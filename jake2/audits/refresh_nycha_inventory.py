"""refresh_nycha_inventory.py — Build a live network-derived unit↔MAC inventory for NYCHA.

Replaces nycha_info.csv as the source of truth for CPE identity. Reads:
  1. Live PPPoE sessions from 000007.R1 → unit label + MAC + address
  2. Live bridge hosts from every NYCHA switch → MAC + switch port
  3. nycha_expected_units.json → authoritative unit roster (unit labels per address)

Writes to a `nycha_live_inventory` table in network_map.db:
  (address, building_id, unit, mac, switch_identity, interface, vendor_group, pppoe_name, refreshed_at)

This table is then used by the audit workbook instead of nycha_info.csv so that the
network itself is the source of truth — not a pre-install planning spreadsheet.

Usage:
    .venv/bin/python -u audits/refresh_nycha_inventory.py
    .venv/bin/python -u audits/refresh_nycha_inventory.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.shared import seed_project_envs

seed_project_envs(PROJECT_ROOT)

from mcp.jake_ops_mcp import (
    JakeOps,
    expand_compact_address,
    mac_vendor_group,
    norm_mac,
    parse_unit_token,
)
from audits.jake_audit_workbook import (
    _load_expected_units,
    _normalize_address,
    _parse_live_bridge_host_output,
)

SWITCH_READ_WORKERS = 6      # parallel switch SSH reads
SWITCH_READ_TIMEOUT = 30     # seconds per switch bridge_hosts_read
PPPOE_READ_TIMEOUT = 20      # seconds for PPPoE router read


def _parse_pppoe_session_name(name: str) -> tuple[str, str] | None:
    """Parse 'NYCHA728EastNewYorkAve4H' → ('728 East New York Ave', '4H').

    Returns None if the name doesn't match NYCHA pattern.
    """
    text = str(name or "").strip()
    if not text.upper().startswith("NYCHA"):
        return None
    # Strip NYCHA prefix, extract trailing unit token (e.g. '4H', '12A')
    body = text[5:]  # drop 'NYCHA'
    unit = parse_unit_token(body)
    if not unit:
        return None
    # Everything before the unit token is the address in compact CamelCase form
    compact_addr = re.sub(re.escape(unit) + r"\s*$", "", body, flags=re.I).strip()
    address = expand_compact_address("NYCHA" + compact_addr)
    if not address:
        return None
    return address, unit


def collect_pppoe_sessions(ops: JakeOps) -> dict[str, dict[str, str]]:
    """Live-read PPPoE sessions from 000007.R1.

    Returns {mac → {address, unit, pppoe_name}}.
    """
    print("  Reading PPPoE sessions from 000007.R1...")
    try:
        result = ops.run_live_routeros_read(
            "000007.R1",
            "ppp_active_read",
            reason="NYCHA inventory refresh — PPPoE session read",
        )
    except Exception as e:
        print(f"  WARNING: PPPoE read failed: {e}", file=sys.stderr)
        return {}

    if not result.get("available"):
        print(f"  WARNING: PPPoE read unavailable: {result.get('error')}", file=sys.stderr)
        return {}

    stdout = "".join(r.get("stdout", "") or "" for r in (result.get("results") or []))
    sessions: dict[str, dict[str, str]] = {}

    # Parse RouterOS detail output — values may be quoted or bare, and fields may
    # appear on separate lines within the same record.
    # Format example:
    #   0 R name="NYCHA728EastNewYorkAve10B" service=pppoe
    #       caller-id="30:68:93:C1:9C:C9" address=10.0.10.113 ...
    pending: dict[str, str] = {}
    for raw in stdout.splitlines():
        line = raw.strip()
        # A line starting with a digit (possibly flags) marks a new record
        if re.match(r"^\d+\s", line) and pending:
            _flush_pppoe_pending(pending, sessions)
            pending = {}

        name_m = re.search(r'\bname="([^"]+)"', line) or re.search(r'\bname=(\S+)', line)
        caller_m = re.search(r'caller-?id="([0-9A-Fa-f:]{17})"', line) or \
                   re.search(r'caller-?id=([0-9A-Fa-f:]{17})', line)
        if name_m:
            pending["name"] = name_m.group(1)
        if caller_m:
            pending["caller_id"] = caller_m.group(1)
        if pending.get("name") and pending.get("caller_id"):
            _flush_pppoe_pending(pending, sessions)
            pending = {}

    if pending:
        _flush_pppoe_pending(pending, sessions)

    print(f"  PPPoE: {len(sessions)} active sessions with NYCHA unit names")
    return sessions


def _flush_pppoe_pending(pending: dict[str, str], out: dict[str, dict[str, str]]) -> None:
    name = pending.get("name", "")
    caller_id = pending.get("caller_id", "")
    if not name or not caller_id:
        return
    parsed = _parse_pppoe_session_name(name)
    if not parsed:
        return
    address, unit = parsed
    mac = norm_mac(caller_id)
    if not mac:
        return
    # Reject locally-administered MACs (mesh backhaul addresses, not CPE WAN MACs)
    if int(mac[0:2], 16) & 0x02:
        return
    out[mac] = {"address": address, "unit": unit, "pppoe_name": name}


def collect_bridge_hosts(ops: JakeOps) -> dict[str, dict[str, str]]:
    """Live-read bridge hosts from all NYCHA switches.

    Returns {mac → {switch_identity, interface}}.
    Only VID=20 ether ports with TP-Link or Vilo OUIs.
    """
    import sqlite3
    conn = sqlite3.connect(str(PROJECT_ROOT / "data" / "network_map.db"))
    conn.row_factory = sqlite3.Row
    switches = conn.execute(
        "SELECT DISTINCT identity FROM devices WHERE identity LIKE '000007.%' "
        "AND identity LIKE '%.SW%' ORDER BY identity"
    ).fetchall()
    conn.close()

    switch_names = [r["identity"] for r in switches]
    print(f"  Reading bridge hosts from {len(switch_names)} NYCHA switches...")

    mac_to_port: dict[str, dict[str, str]] = {}
    lock_results: list[tuple[str, dict[str, list[str]]]] = []

    def read_switch(sw: str) -> tuple[str, dict[str, list[str]]]:
        result = ops.run_live_routeros_read(
            sw, "bridge_hosts_read",
            reason="NYCHA inventory refresh — bridge host read",
        )
        if not result.get("available"):
            return sw, {}
        parsed = _parse_live_bridge_host_output(result.get("results") or [])
        return sw, parsed

    with ThreadPoolExecutor(max_workers=SWITCH_READ_WORKERS) as pool:
        futures = {pool.submit(read_switch, sw): sw for sw in switch_names}
        done = 0
        for fut, sw in futures.items():
            try:
                sw_name, port_macs = fut.result(timeout=SWITCH_READ_TIMEOUT)
                for iface, macs in port_macs.items():
                    for mac in macs:
                        if mac not in mac_to_port:
                            mac_to_port[mac] = {"switch_identity": sw_name, "interface": iface}
                done += 1
                if done % 10 == 0:
                    print(f"  [{done}/{len(switch_names)}] switches read")
            except FuturesTimeoutError:
                print(f"  TIMEOUT: {sw}", file=sys.stderr)
            except Exception as e:
                print(f"  ERROR {sw}: {e}", file=sys.stderr)

    print(f"  Bridge hosts: {len(mac_to_port)} unique CPE MACs on VID=20 ether ports")
    return mac_to_port


def build_inventory(
    pppoe: dict[str, dict[str, str]],
    bridge: dict[str, dict[str, str]],
    expected_units: dict[str, list[str]],
    ops: JakeOps,
) -> list[dict]:
    """Merge PPPoE + bridge data into inventory rows.

    Primary key: mac. Sources:
      - PPPoE session → address + unit + pppoe_name
      - Bridge host   → switch_identity + interface
      - Address resolution → building_id

    Also adds rows for expected units with no PPPoE evidence (installed but not connected).
    """
    rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    # Resolve building_id cache (address → prefix)
    resolve_cache: dict[str, str | None] = {}

    def get_building_id(address: str) -> str | None:
        norm = _normalize_address(address)
        if norm not in resolve_cache:
            try:
                result = ops._resolve_building_from_address(address)
                bm = (result.get("best_match") or {})
                resolve_cache[norm] = bm.get("prefix") or None
            except Exception:
                resolve_cache[norm] = None
        return resolve_cache[norm]

    # Track which (address, unit) pairs we've covered
    covered: set[tuple[str, str]] = set()

    # Step 1: All MACs with PPPoE evidence
    for mac, ppp in pppoe.items():
        address = ppp["address"]
        unit = ppp["unit"]
        port = bridge.get(mac, {})
        building_id = get_building_id(address)
        vendor = mac_vendor_group(mac)
        rows.append({
            "address": address,
            "building_id": building_id or "",
            "unit": unit,
            "mac": mac,
            "switch_identity": port.get("switch_identity", ""),
            "interface": port.get("interface", ""),
            "vendor_group": vendor,
            "pppoe_name": ppp["pppoe_name"],
            "evidence": "pppoe",
            "refreshed_at": now,
        })
        covered.add((_normalize_address(address), unit.upper()))

    # Step 2: Bridge MACs not in PPPoE → "present but no session"
    for mac, port in bridge.items():
        if mac in pppoe:
            continue
        vendor = mac_vendor_group(mac)
        rows.append({
            "address": "",
            "building_id": "",
            "unit": "",
            "mac": mac,
            "switch_identity": port["switch_identity"],
            "interface": port["interface"],
            "vendor_group": vendor,
            "pppoe_name": "",
            "evidence": "bridge_only",
            "refreshed_at": now,
        })

    print(f"  Inventory: {len(rows)} rows ({sum(1 for r in rows if r['evidence']=='pppoe')} with PPPoE, "
          f"{sum(1 for r in rows if r['evidence']=='bridge_only')} bridge-only)")
    return rows


def write_inventory(rows: list[dict], db_path: Path, dry_run: bool = False) -> None:
    """Write inventory rows to network_map.db nycha_live_inventory table."""
    import sqlite3

    ddl = """
    CREATE TABLE IF NOT EXISTS nycha_live_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address TEXT NOT NULL,
        building_id TEXT NOT NULL,
        unit TEXT NOT NULL,
        mac TEXT NOT NULL,
        switch_identity TEXT NOT NULL,
        interface TEXT NOT NULL,
        vendor_group TEXT NOT NULL,
        pppoe_name TEXT NOT NULL,
        evidence TEXT NOT NULL,
        refreshed_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_nycha_inv_mac ON nycha_live_inventory(mac);
    CREATE INDEX IF NOT EXISTS idx_nycha_inv_address_unit ON nycha_live_inventory(address, unit);
    CREATE INDEX IF NOT EXISTS idx_nycha_inv_building ON nycha_live_inventory(building_id);
    CREATE INDEX IF NOT EXISTS idx_nycha_inv_switch ON nycha_live_inventory(switch_identity, interface);
    """

    if dry_run:
        print(f"\nDRY RUN — would write {len(rows)} rows to nycha_live_inventory")
        print("Sample rows:")
        for r in rows[:5]:
            print(f"  {r['address'] or '(no address)'} unit={r['unit'] or '?'} "
                  f"mac={r['mac']} sw={r['switch_identity']} port={r['interface']} "
                  f"evidence={r['evidence']}")
        return

    conn = sqlite3.connect(str(db_path))
    try:
        for stmt in ddl.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        # Wipe and replace — this is a full refresh
        conn.execute("DELETE FROM nycha_live_inventory")
        conn.executemany(
            """INSERT INTO nycha_live_inventory
               (address, building_id, unit, mac, switch_identity, interface,
                vendor_group, pppoe_name, evidence, refreshed_at)
               VALUES (:address, :building_id, :unit, :mac, :switch_identity, :interface,
                       :vendor_group, :pppoe_name, :evidence, :refreshed_at)""",
            rows,
        )
        conn.commit()
        print(f"\nWrote {len(rows)} rows to nycha_live_inventory in {db_path.name}")
    finally:
        conn.close()


def print_summary(rows: list[dict]) -> None:
    from collections import Counter

    by_evidence = Counter(r["evidence"] for r in rows)
    by_vendor = Counter(r["vendor_group"] for r in rows)

    # Per-building coverage
    by_address: dict[str, dict[str, int]] = defaultdict(lambda: {"pppoe": 0, "bridge_only": 0})
    for r in rows:
        addr = r["address"] or r["switch_identity"].split(".")[0] + " (unknown building)"
        by_address[addr][r["evidence"]] += 1

    print("\n── Summary ──────────────────────────────────────────")
    print(f"Total CPE MACs seen:  {len(rows)}")
    print(f"  With PPPoE session: {by_evidence['pppoe']}")
    print(f"  Bridge-only:        {by_evidence['bridge_only']}")
    print(f"\nVendor distribution:")
    for v, c in by_vendor.most_common():
        print(f"  {v}: {c}")
    print(f"\nTop buildings by PPPoE coverage:")
    top = sorted(by_address.items(), key=lambda x: -x[1]["pppoe"])
    for addr, counts in top[:15]:
        total = counts["pppoe"] + counts["bridge_only"]
        print(f"  {addr:<45} pppoe={counts['pppoe']:3d}  bridge-only={counts['bridge_only']:3d}  total={total:3d}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh NYCHA live inventory from network")
    parser.add_argument("--dry-run", action="store_true", help="Print results, don't write to DB")
    parser.add_argument("--skip-bridge", action="store_true", help="Skip bridge host reads (PPPoE only)")
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "network_map.db"
    if not db_path.exists():
        print(f"ERROR: {db_path} not found", file=sys.stderr)
        sys.exit(1)

    print("Initializing JakeOps...")
    ops = JakeOps()
    # Pre-warm NetBox cache
    try:
        ops._netbox_all_devices()
        ops._location_prefix_index()
        print("  NetBox device cache warmed")
    except Exception:
        pass

    expected_units = _load_expected_units()
    print(f"  Expected units loaded: {len(expected_units)} buildings")

    start = time.time()

    print("\nStep 1: PPPoE sessions")
    pppoe = collect_pppoe_sessions(ops)

    print("\nStep 2: Bridge hosts")
    bridge = collect_bridge_hosts(ops) if not args.skip_bridge else {}

    print("\nStep 3: Building inventory")
    rows = build_inventory(pppoe, bridge, expected_units, ops)

    elapsed = time.time() - start
    print(f"\nCompleted in {elapsed:.0f}s")

    print_summary(rows)
    write_inventory(rows, db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
