from __future__ import annotations

import concurrent.futures
import json
import os
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from diagnosis.workbook_adapter import build_workbook_diagnosis_result
from mcp.jake_ops_mcp import (
    TAUC_NYCHA_AUDIT_CSV,
    _current_tauc_audit_csv,
    canonical_identity,
    find_local_online_cpe_row,
    is_probable_customer_bridge_host,
    load_nycha_info_rows,
    load_tauc_nycha_audit_rows,
    normalize_address_text,
    norm_mac,
    parse_unit_token,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = Path(__file__).resolve().parent
EXPECTED_UNITS_PATH = PROJECT_ROOT / "data" / "nycha_expected_units.json"
DIAGNOSIS_RENDERING_SITE_REGISTRY_PATH = Path(
    os.environ.get(
        "JAKE_DIAGNOSIS_RENDERING_SITE_REGISTRY",
        str(PROJECT_ROOT / "data" / "diagnosis_rendering_sites.json"),
    )
)
DEFAULT_TEMPLATE_WORKBOOK = Path(
    os.environ.get(
        "JAKE_AUDIT_TEMPLATE_WORKBOOK",
        str(PROJECT_ROOT / "tests" / "fixtures" / "audit" / "nycha_template.xlsx"),
    )
)
USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK = False
CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK = True
USE_DIAGNOSIS_OVERRIDE_FOR_HIGH_SEVERITY = True
USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING = False


def _load_diagnosis_rendering_enabled_sites() -> set[str]:
    path = DIAGNOSIS_RENDERING_SITE_REGISTRY_PATH
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    sites = payload.get("sites") if isinstance(payload, dict) else []
    enabled: set[str] = set()
    for row in list(sites or []):
        if not isinstance(row, dict):
            continue
        address = normalize_address_text(row.get("address"))
        if address and bool(row.get("rendering_enabled")):
            enabled.add(address)
    return enabled


def _diagnosis_rendering_enabled_for_address(address_text: str) -> bool:
    if USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING:
        return True
    return normalize_address_text(address_text) in _load_diagnosis_rendering_enabled_sites()


def _require_openpyxl():
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.table import Table, TableStyleInfo

    return {
        "Workbook": Workbook,
        "load_workbook": load_workbook,
        "Alignment": Alignment,
        "Font": Font,
        "PatternFill": PatternFill,
        "Table": Table,
        "TableStyleInfo": TableStyleInfo,
    }


@dataclass
class AuditRow:
    unit_key: str
    unit_label: str
    mac_cpe: str           # Inventory/CSV MAC — scanned during install
    pppoe_unit: str
    notes: str
    image_ap_make: str
    image_ap_sticker_apartment: str
    image_ap_mac: str      # Controller MAC — from Vilo snapshot or TAUC/TP-Link export
    inventory_mac_verification: str
    implication: str
    action: str
    switch_port: str = ""
    mac_live: str = ""     # Live MAC — physically seen on the switch port right now
    mac_controller: str = ""  # Controller-reported MAC (Vilo/TP-Link) when different from inventory
    legacy_status: str = ""
    diagnosis_status: str = ""
    diagnosis_confidence: str = ""
    diagnosis_explanation: str = ""
    diagnosis_dispatch_required: bool | None = None
    diagnosis_dispatch_priority: str = ""
    diagnosis_backend_action: str = ""
    diagnosis_field_action: str = ""
    reality_contradictions_count: int = 0
    reality_unknowns_count: int = 0
    evidence_unknowns: list[str] | None = None
    evidence_unknowns_summary: str = ""
    evidence_contradictions: list[str] | None = None
    evidence_contradictions_summary: str = ""
    evidence_stale_sources: list[str] | None = None
    evidence_stale_sources_summary: str = ""
    override_applied: bool = False
    override_reason: str = ""
    override_confidence: str = ""
    cutover_safe: bool = False
    cutover_block_reason: str = ""


@dataclass
class LayoutSpec:
    kind: str
    header_row: int
    data_start_row: int
    title_columns: tuple[str, str, str, str]
    headers: list[str]
    donor_sheet_name: str | None = None
    donor_units: list[tuple[str, str]] | None = None


@dataclass
class LiveContext:
    building_id: str | None
    site_id: str | None
    online_units_by_token: dict[str, dict[str, Any]]
    exact_matches_by_unit: dict[str, dict[str, Any]]
    active_alert_count: int
    building_device_count: int
    site_online_count: int | None
    inferred_switch_identity: str | None
    live_port_macs_by_interface: dict[str, list[str]]
    switch_identities_by_label_prefix: dict[str, str]
    live_port_macs_by_switch_identity: dict[str, dict[str, list[str]]]
    controller_verification_by_mac: dict[str, dict[str, Any]]
    live_failures: list[dict[str, str]]
    port_observations_by_unit: dict[str, dict[str, Any]] | None = None
    auth_observations_by_unit: dict[str, dict[str, Any]] | None = None
    dhcp_observations_by_unit: dict[str, dict[str, Any]] | None = None
    captured_at_timestamp: str | None = None
    historical_search_completed: dict[str, bool] | bool | None = None
    historical_locations_by_unit: dict[str, list[dict[str, Any]]] | None = None
    expected_port_search_completed_by_unit: dict[str, bool] | None = None
    switch_scope_search_completed_by_unit: dict[str, bool] | None = None
    global_search_completed_by_unit: dict[str, bool] | None = None
    # True if the DB scan found any customer bridge-host MACs for this building's switches.
    # Used to gate "UNPLUGGED / BAD CABLE" — only valid when we know the switch is reachable
    # and was returning bridge data at scan time. More stable than per-run SSH reads.
    building_has_db_bridge_hosts: bool = False


@dataclass
class CallResult:
    ok: bool
    value: Any
    source: str
    classification: str | None = None
    detail: str | None = None


@dataclass
class SnapshotLoadResult:
    by_mac: dict[str, dict[str, Any]]
    failure: dict[str, str] | None = None
    snapshot_timestamp: str | None = None


def _call_with_timeout(source: str, timeout_s: float, fn, *args, **kwargs) -> CallResult:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, *args, **kwargs)
        try:
            return CallResult(ok=True, value=future.result(timeout=timeout_s), source=source)
        except concurrent.futures.TimeoutError:
            return CallResult(
                ok=False,
                value=None,
                source=source,
                classification="missing_runtime",
                detail=f"{source} timed out after {timeout_s:.1f}s",
            )
        except Exception as exc:
            return CallResult(
                ok=False,
                value=None,
                source=source,
                classification="code_error",
                detail=str(exc),
            )


def _load_vilo_inventory_snapshot() -> SnapshotLoadResult:
    explicit = Path(os.environ["JAKE_VILO_INVENTORY_SNAPSHOT"]) if os.environ.get("JAKE_VILO_INVENTORY_SNAPSHOT") else None
    candidates = [explicit] if explicit else sorted((PROJECT_ROOT / "data").glob("vilo_inventory_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        # WHY: The Vilo snapshot is corroboration only, but its absence must still be explicit so missing corroboration is not mistaken for clean evidence.
        return SnapshotLoadResult(
            by_mac={},
            failure={
                "source": "vilo_inventory_snapshot",
                "classification": "data_dependency",
                "detail": "No Vilo inventory snapshot is available.",
            },
            snapshot_timestamp=None,
        )
    selected = candidates[0]
    try:
        payload = json.loads(selected.read_text())
        rows = payload if isinstance(payload, list) else payload.get("rows") or payload.get("device_list") or payload.get("data", {}).get("device_list") or []
    except Exception as exc:
        # WHY: Snapshot parse failures must not silently flatten into empty inventory because that hides a corroboration failure as if no devices existed.
        return SnapshotLoadResult(
            by_mac={},
            failure={
                "source": "vilo_inventory_snapshot",
                "classification": "data_dependency",
                "detail": f"Failed to parse Vilo snapshot: {exc}",
            },
            snapshot_timestamp=None,
        )
    snapshot_timestamp = datetime.fromtimestamp(selected.stat().st_mtime, tz=timezone.utc).isoformat()
    by_mac: dict[str, dict[str, Any]] = {}
    for row in rows:
        mac = norm_mac(row.get("device_mac") or "")
        if mac:
            enriched = dict(row)
            if not any(str(enriched.get(key) or "").strip() for key in ("last_seen", "lastSeen", "updated_at", "timestamp")):
                enriched["timestamp"] = snapshot_timestamp
            by_mac[mac] = enriched
    return SnapshotLoadResult(by_mac=by_mac, snapshot_timestamp=snapshot_timestamp)


def _build_controller_verification(source_rows: list[dict[str, str]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    # WHY: Vilo snapshots and TAUC audit rows are corroboration only. They can support or contradict a conclusion, but they must never replace live edge-port evidence.
    vilo_snapshot_result = _load_vilo_inventory_snapshot()
    vilo_snapshot = vilo_snapshot_result.by_mac
    tauc_rows = load_tauc_nycha_audit_rows()
    tauc_csv_path = _current_tauc_audit_csv()
    tauc_snapshot_timestamp = (
        datetime.fromtimestamp(tauc_csv_path.stat().st_mtime, tz=timezone.utc).isoformat()
        if tauc_csv_path.exists()
        else None
    )
    tauc_by_network = {
        str(row.get("networkName") or "").strip(): (
            dict(row)
            if any(str(row.get(key) or "").strip() for key in ("last_seen", "lastSeen", "updated_at", "timestamp"))
            else {**dict(row), "timestamp": tauc_snapshot_timestamp}
        )
        for row in tauc_rows
        if str(row.get("networkName") or "").strip()
    }
    verification: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        mac = norm_mac(row.get("MAC Address") or row.get("mac") or "")
        if not mac:
            continue
        network_name = str(row.get("PPPoE") or "").strip()
        serial = str(row.get("AP Serial Number") or "").strip()
        vendor = str(row.get("AP Make") or "").strip().lower()
        entry = {
            "vendor": vendor,
            "status": "unverified",
            "label": "Not verified",
        }
        if "vilo" in vendor:
            snap = vilo_snapshot.get(mac)
            if snap:
                note = str(snap.get("notes") or "").strip()
                snap_serial = str(snap.get("device_sn") or "").strip()
                if note.lower() == network_name.lower() and (not serial or not snap_serial or snap_serial == serial):
                    entry = {
                        "vendor": "vilo",
                        "status": "match",
                        "label": "Vilo inventory match",
                        "snapshot_row": snap,
                    }
                else:
                    entry = {
                        "vendor": "vilo",
                        "status": "mismatch",
                        "label": "Vilo inventory mismatch",
                        "snapshot_row": snap,
                    }
            elif vilo_snapshot_result.failure:
                entry = {
                    "vendor": "vilo",
                    "status": "lookup_failed",
                    "label": "Vilo inventory unavailable",
                }
        elif "tp-link" in vendor or "tplink" in vendor:
            tauc = tauc_by_network.get(network_name)
            if tauc:
                tauc_mac = norm_mac(tauc.get("tauc_mac") or tauc.get("mac") or "")
                expected_unit = _canonical_unit_token(parse_unit_token(tauc.get("expected_unit")))
                row_unit = _canonical_unit_token(parse_unit_token(row.get("Unit")))
                if (not tauc_mac or tauc_mac == mac) and (not expected_unit or expected_unit == row_unit):
                    entry = {
                        "vendor": "tplink_hc220",
                        "status": "match",
                        "label": "TAUC audit match",
                        "snapshot_row": tauc,
                    }
                else:
                    entry = {
                        "vendor": "tplink_hc220",
                        "status": "mismatch",
                        "label": "TAUC audit mismatch",
                        "snapshot_row": tauc,
                    }
        verification[mac] = entry
    failures = [vilo_snapshot_result.failure] if vilo_snapshot_result.failure else []
    return verification, failures


def _best_edge_sighting_for_mac(ops: Any, mac: str) -> dict[str, Any] | None:
    normalized = norm_mac(mac or "")
    if not normalized:
        return None
    scan_id = ops.latest_scan_id()
    rows = [
        dict(r)
        for r in ops.db.execute(
            """
            select d.identity, bh.ip, bh.on_interface, bh.vid, bh.mac, bh.local, bh.external
            from bridge_hosts bh
            left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
            where bh.scan_id=? and lower(bh.mac)=lower(?) and bh.local=0
            order by d.identity, bh.on_interface
            """,
            (scan_id, normalized),
        ).fetchall()
    ]
    probable = [row for row in rows if is_probable_customer_bridge_host(row)]
    # WHY: Edge-port evidence outranks switch-local sightings because switch-local learning can reflect internal or transit visibility rather than the subscriber-facing drop.
    edge = [row for row in probable if str(row.get("on_interface") or "").startswith("ether")]
    if edge:
        return edge[0]
    return probable[0] if probable else None


def _infer_switch_identity_for_address(ops: Any, source_rows: list[dict[str, str]]) -> str | None:
    counts: dict[str, int] = {}
    for row in source_rows:
        hit = _best_edge_sighting_for_mac(ops, row.get("MAC Address") or row.get("mac") or "")
        if not hit:
            continue
        identity = canonical_identity(hit.get("identity"))
        if identity:
            counts[identity] = counts.get(identity, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _live_port_macs_for_switch(ops: Any, switch_identity: str) -> dict[str, list[str]]:
    if not switch_identity:
        return {}
    live = _call_with_timeout(
        "run_live_routeros_read",
        8.0,
        ops.run_live_routeros_read,
        switch_identity,
        "bridge_hosts_read",
        None,
        "Live bridge-host read for audit workbook generation.",
    )
    parsed = _parse_live_bridge_host_output(((live.value or {}) if live.ok else {}).get("results") or [])
    if parsed:
        return parsed
    scan_id = ops.latest_scan_id()
    rows = [
        dict(r)
        for r in ops.db.execute(
            """
            select d.identity, bh.on_interface, bh.vid, bh.mac, bh.local, bh.external
            from bridge_hosts bh
            left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
            where bh.scan_id=? and d.identity=? and bh.local=0 and bh.on_interface like 'ether%'
            order by bh.on_interface, bh.mac
            """,
            (scan_id, switch_identity),
        ).fetchall()
    ]
    by_interface: dict[str, list[str]] = {}
    for row in rows:
        if not is_probable_customer_bridge_host(row):
            continue
        interface = str(row.get("on_interface") or "").strip()
        mac = norm_mac(row.get("mac") or "")
        if not interface or not mac:
            continue
        bucket = by_interface.setdefault(interface, [])
        if mac not in bucket:
            bucket.append(mac)
    return by_interface


def _parse_live_bridge_host_output(results: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_interface: dict[str, list[str]] = {}

    def _add_candidate(interface: str, mac: str, vid: str) -> None:
        if not interface.startswith("ether") or not mac or vid != "20":
            return
        synthetic = {"on_interface": interface, "mac": mac, "local": False, "external": False}
        if not is_probable_customer_bridge_host(synthetic):
            return
        bucket = by_interface.setdefault(interface, [])
        if mac not in bucket:
            bucket.append(mac)

    for result in results:
        stdout = str(result.get("stdout") or "")
        if not stdout:
            continue
        pending_mac = ""
        pending_interface = ""
        pending_vid = ""
        for raw in stdout.splitlines():
            line = raw.strip()
            if not line:
                continue
            if "mac-address=" in line and "on-interface=" in line:
                mac_match = re.search(r"mac-address=([0-9A-F:]{17})", line, re.I)
                iface_match = re.search(r"on-interface=([A-Za-z0-9._-]+)", line, re.I)
                vid_match = re.search(r"\bvid=(\d+)\b", line, re.I)
                if mac_match and iface_match:
                    mac = norm_mac(mac_match.group(1))
                    iface = iface_match.group(1)
                    vid = vid_match.group(1) if vid_match else ""
                    _add_candidate(iface, mac, vid)
                    continue
            if "mac-address=" in line:
                mac_match = re.search(r"mac-address=([0-9A-F:]{17})", line, re.I)
                vid_match = re.search(r"\bvid=(\d+)\b", line, re.I)
                if mac_match:
                    pending_mac = norm_mac(mac_match.group(1))
                    pending_vid = vid_match.group(1) if vid_match else ""
                    pending_interface = ""
                    continue
            if "on-interface=" in line and pending_mac:
                iface_match = re.search(r"on-interface=([A-Za-z0-9._-]+)", line, re.I)
                if iface_match:
                    pending_interface = iface_match.group(1)
                    _add_candidate(pending_interface, pending_mac, pending_vid)
                pending_mac = ""
                pending_interface = ""
                pending_vid = ""
                continue
            compact_match = re.search(
                r"\b([0-9A-F:]{17})\s+(\d+)?\s*(ether\d+)\b",
                line,
                re.I,
            )
            if compact_match:
                mac = norm_mac(compact_match.group(1))
                vid = str(compact_match.group(2) or "")
                iface = compact_match.group(3)
                _add_candidate(iface, mac, vid)
                continue
            detail_match = re.search(
                r"\b([0-9A-F:]{17})\b.*\bvid=(\d+)\b.*\binterface=(ether\d+)\b",
                line,
                re.I,
            )
            if detail_match:
                mac = norm_mac(detail_match.group(1))
                vid = detail_match.group(2)
                iface = detail_match.group(3)
                _add_candidate(iface, mac, vid)
    return by_interface


def _switch_port_to_interface(label: str | None) -> str | None:
    match = re.fullmatch(r"SW\d+-(\d+)", str(label or "").strip(), re.I)
    if not match:
        return None
    return f"ether{int(match.group(1))}"


def _switch_port_prefix(label: str | None) -> str | None:
    match = re.fullmatch(r"(SW\d+)-\d+", str(label or "").strip(), re.I)
    if not match:
        return None
    return match.group(1).upper()


def _map_switch_label_prefixes(
    device_names: list[str] | None,
    fallback_identity: str | None = None,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    ordered = [canonical_identity(name) for name in (device_names or []) if canonical_identity(name)]
    switch_identities = [name for name in ordered if re.search(r"\.SW\d+$", name, re.I)]
    switch_identities.sort(key=lambda name: int(re.search(r"\.SW(\d+)$", name, re.I).group(1)))
    for idx, identity in enumerate(switch_identities, start=1):
        mapping[f"SW{idx}"] = identity
    if fallback_identity and "SW1" not in mapping:
        mapping["SW1"] = fallback_identity
    return mapping


def _parse_mac_octets(mac: str | None) -> list[int] | None:
    normalized = norm_mac(mac or "")
    if not normalized or len(normalized.split(":")) != 6:
        return None
    try:
        return [int(part, 16) for part in normalized.split(":")]
    except ValueError:
        return None


def _known_mac_bug_kind(expected_mac: str | None, observed_mac: str | None) -> str | None:
    expected = _parse_mac_octets(expected_mac)
    observed = _parse_mac_octets(observed_mac)
    if not expected or not observed or expected == observed:
        return None
    differing = [idx for idx, (lhs, rhs) in enumerate(zip(expected, observed)) if lhs != rhs]
    if len(differing) != 1:
        return None
    idx = differing[0]
    if idx not in {0, 5}:
        return None
    if abs(expected[idx] - observed[idx]) != 1:
        return None
    return "first_octet" if idx == 0 else "last_octet"


def _normalize_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _canonicalize_address_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = text.replace(".", " ")
    text = re.sub(r"\bst\s+johns\b", "saint johns", text)
    text = re.sub(r"\bst\s+marks\b", "saint marks", text)
    text = re.sub(r"\be\s+new\s+york\b", "east new york", text)
    text = re.sub(r"\beast\s+ny\b", "east new york", text)
    text = re.sub(r"\be\s+ny\b", "east new york", text)
    text = re.sub(r"\bnew\s+york\b", "newyork", text)
    text = re.sub(r"\beast\s+newyork\b", "eastnewyork", text)
    text = re.sub(r"\b(street|st|avenue|ave|road|rd|place|pl)\b", "", text)
    text = re.sub(r"[^a-z0-9\- ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_address(value: str | None) -> str:
    return _canonicalize_address_text(value)


def _address_parts(value: str | None) -> tuple[int | None, int | None, str]:
    text = _canonicalize_address_text(value)
    match = re.match(r"^\s*(\d+)(?:\s*-\s*(\d+))?\s+(.*)$", text)
    if not match:
        return None, None, text
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else None
    street = (match.group(3) or "").strip()
    return start, end, street


def _sheet_title_for_address(address_text: str) -> str:
    text = str(address_text or "").strip()
    text = re.sub(r"\bRoad\b", "Rd", text, flags=re.I)
    text = re.sub(r"\bAvenue\b", "Ave", text, flags=re.I)
    text = re.sub(r"\bStreet\b", "St", text, flags=re.I)
    text = re.sub(r"\bPlace\b", "Pl", text, flags=re.I)
    return text[:31]


def _canonical_unit_token(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = text.replace("UNIT", "").replace(" ", "")
    match = re.match(r"^0*(\d+)([A-Z]+)?$", text)
    if match:
        number = str(int(match.group(1)))
        suffix = match.group(2) or ""
        return f"{number}{suffix}"
    return text


def _extract_pppoe_unit(pppoe_label: str | None) -> str:
    text = str(pppoe_label or "").strip()
    match = re.search(r"(\d+[A-Za-z]+)$", text)
    if match:
        return match.group(1).upper()
    return ""


def _normalize_mac(value: str | None) -> str:
    hexed = re.sub(r"[^0-9A-Fa-f]", "", str(value or ""))
    if len(hexed) != 12:
        return str(value or "").strip()
    return ":".join(hexed[i:i + 2] for i in range(0, 12, 2)).upper()


def _load_expected_units() -> dict[str, list[str]]:
    if not EXPECTED_UNITS_PATH.exists():
        return {}
    try:
        return json.loads(EXPECTED_UNITS_PATH.read_text())
    except Exception:
        return {}


def _expected_units_for_address(address_text: str) -> list[str]:
    """Return the pre-build expected unit list for this address, or [] if not found."""
    expected = _load_expected_units()
    normalized = _normalize_address(address_text)
    # First try exact normalized match
    for addr, units in expected.items():
        if _normalize_address(addr) == normalized:
            return list(units)
    # Try partial/block range matching using _address_parts
    req_start, req_end, req_street = _address_parts(address_text)
    if not req_street:
        return []
    for addr, units in expected.items():
        row_start, row_end, row_street = _address_parts(addr)
        if row_street != req_street:
            continue
        if req_end is not None and row_start == req_start:
            return list(units)
        if req_start is not None and row_start is not None:
            effective_end = row_end if row_end is not None else row_start
            if row_start <= req_start <= effective_end:
                if row_end is not None and (req_start % 2) != (row_start % 2):
                    continue
                return list(units)
    return []


def _load_live_inventory_rows_for_address(address_text: str) -> list[dict[str, str]]:
    """Read CPE inventory from nycha_live_inventory table in network_map.db.

    Returns rows shaped like nycha_info rows: {Address, Unit, MAC Address, PPPoE}.
    Only returns rows that have a PPPoE name (i.e. have confirmed unit assignment).
    Falls back silently to [] if the table doesn't exist yet (pre-first-refresh).
    """
    import sqlite3
    db_path = PROJECT_ROOT / "data" / "network_map.db"
    if not db_path.exists():
        return []
    normalized = _normalize_address(address_text)
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT address, unit, mac, pppoe_name FROM nycha_live_inventory "
            "WHERE evidence='pppoe' AND address != '' ORDER BY unit"
        ).fetchall()
        conn.close()
    except Exception:
        return []

    result = []
    for r in rows:
        if _normalize_address(r["address"]) == normalized:
            result.append({
                "Address": r["address"],
                "Unit": r["unit"],
                "MAC Address": r["mac"].upper() if r["mac"] else "",
                "PPPoE": r["pppoe_name"],
            })
    return result


def _iter_nycha_rows_for_address(address_text: str) -> list[dict[str, str]]:
    normalized = _normalize_address(address_text)
    source_rows = load_nycha_info_rows()
    rows = [row for row in source_rows if _normalize_address(row.get("Address")) == normalized]
    if rows:
        return rows

    req_start, req_end, req_street = _address_parts(address_text)
    if not req_street:
        # No CSV rows — try live inventory DB before giving up
        return _load_live_inventory_rows_for_address(address_text)

    # If the donor sheet is a range/block, accept rows anchored to the same street and start address.
    if req_end is not None:
        anchored = []
        for row in source_rows:
            row_start, _row_end, row_street = _address_parts(row.get("Address"))
            if row_street == req_street and row_start == req_start:
                anchored.append(row)
        if anchored:
            return anchored

    # If the donor sheet is a single address, allow it to map into a source block range on the same street.
    # WHY: A range like "602-614 Howard Ave" covers only even numbers (602, 606, 610, 614) while
    # "583-611 Howard Ave" covers only odd numbers (583, 587, 591...). Parity of the queried address
    # must match parity of the range start — otherwise "606 Howard Ave" would wrongly match the odd
    # range 583-611 in addition to (or instead of) the correct even range 602-614.
    if req_start is not None:
        block_rows = []
        for row in source_rows:
            row_start, row_end, row_street = _address_parts(row.get("Address"))
            if row_street != req_street or row_start is None:
                continue
            effective_end = row_end if row_end is not None else row_start
            if row_start <= req_start <= effective_end:
                # Parity check: only match if requested number has same parity as range start.
                if row_end is not None and (req_start % 2) != (row_start % 2):
                    continue
                block_rows.append(row)
        if block_rows:
            return block_rows

    # CSV exhausted — fall back to live inventory DB
    return _load_live_inventory_rows_for_address(address_text)


def _find_donor_sheet(template_path: Path, address_text: str) -> tuple[str | None, Any | None]:
    if not template_path.exists():
        return None, None
    xl = _require_openpyxl()
    wb = xl["load_workbook"](template_path)
    normalized_target = _normalize_address(address_text)
    for sheet_name in wb.sheetnames:
        if _normalize_address(sheet_name) == normalized_target:
            return sheet_name, wb[sheet_name]
    return None, None


def _infer_layout(address_text: str, template_path: Path) -> LayoutSpec:
    donor_name, donor_sheet = _find_donor_sheet(template_path, address_text)
    if donor_sheet is not None:
        if str(donor_sheet["A3"].value or "").strip() == "Physical Unit":
            donor_units: list[tuple[str, str]] = []
            row = 4
            while True:
                unit = str(donor_sheet[f"A{row}"].value or "").strip()
                if not unit:
                    break
                donor_units.append(("", unit))
                row += 1
            return LayoutSpec(
                kind="physical",
                header_row=3,
                data_start_row=4,
                title_columns=("B", "C", "D", "E"),
                headers=[
                    "Physical Unit",
                    "MAC CPE",
                    "PPPoE Unit",
                    "Notes - On Site",
                    "Image AP Make",
                    "Image AP Sticker Apartment",
                    "Image AP MAC",
                    "Inventory MAC Verification",
                    "Implication",
                    "Action",
                ],
                donor_sheet_name=donor_name,
                donor_units=donor_units,
            )
        header_row = 2 if str(donor_sheet["A2"].value or "").strip() == "Switch Port" else 3
        donor_units: list[tuple[str, str]] = []
        row = header_row + 1
        while True:
            left = str(donor_sheet[f"A{row}"].value or "").strip()
            unit = str(donor_sheet[f"B{row}"].value or "").strip()
            if not left and not unit:
                break
            donor_units.append((left, unit))
            row += 1
        return LayoutSpec(
            kind="switch",
            header_row=header_row,
            data_start_row=header_row + 1,
            title_columns=("C", "D", "E", "F") if header_row == 3 else ("C", "D", "E", "F"),
            headers=[
                "Switch Port",
                "Unit",
                "MAC CPE",
                "PPPoE Unit",
                "Notes - On Site",
                "Image AP Make",
                "Image AP Sticker Apartment",
                "Image AP MAC",
                "Inventory MAC Verification",
                "Implication",
                "Action",
            ],
            donor_sheet_name=donor_name,
            donor_units=donor_units,
        )

    if "-" in address_text:
        return LayoutSpec(
            kind="switch",
            header_row=3,
            data_start_row=4,
            title_columns=("C", "D", "E", "F"),
            headers=[
                "Switch Port",
                "Unit",
                "MAC CPE",
                "PPPoE Unit",
                "Notes - On Site",
                "Image AP Make",
                "Image AP Sticker Apartment",
                "Image AP MAC",
                "Inventory MAC Verification",
                "Implication",
                "Action",
            ],
        )
    # WHY: Default to switch layout even without a template. The reverse MAC lookup and
    # Bigmac fallback populate switch_port for seen units, so switch layout (with the
    # Switch Port column) is always more informative than physical layout.
    return LayoutSpec(
        kind="switch",
        header_row=2,
        data_start_row=3,
        title_columns=("C", "D", "E", "F"),
        headers=[
            "Switch Port",
            "Unit",
            "MAC CPE",
            "PPPoE Unit",
            "Notes - On Site",
            "Image AP Make",
            "Image AP Sticker Apartment",
            "Image AP MAC",
            "Inventory MAC Verification",
            "Implication",
            "Action",
        ],
    )


def _classify_row(source_row: dict[str, str], unit_label: str) -> AuditRow:
    mac = _normalize_mac(source_row.get("MAC Address") or source_row.get("mac"))
    ap_make = str(source_row.get("AP Make") or "").strip()
    pppoe = str(source_row.get("PPPoE") or "").strip()
    pppoe_unit = _extract_pppoe_unit(pppoe)
    opt_out = str(source_row.get("Opt-Outs") or "").strip()
    progress = str(source_row.get("Progress") or "").strip().upper()
    unit_key = _canonical_unit_token(unit_label)

    image_ap_make = ""
    image_ap_sticker_apartment = ""
    image_ap_mac = ""
    inventory_mac_verification = ""
    implication = ""
    action = "None"

    if opt_out:
        return AuditRow(
            unit_key=unit_key,
            unit_label=unit_label,
            mac_cpe="OPT OUT",
            pppoe_unit="",
            notes="NOT INSTALLED",
            image_ap_make=image_ap_make,
            image_ap_sticker_apartment=image_ap_sticker_apartment,
            image_ap_mac=image_ap_mac,
            inventory_mac_verification=inventory_mac_verification,
            implication=implication,
            action=action,
        )

    if not mac:
        note = "NOT INSTALLED" if "COMPLETE" not in progress else "???"
        implication = "Inventory row exists but no scanned CPE MAC is present." if note == "???" else ""
        action = "Verify install status" if note == "???" else "None"
        return AuditRow(
            unit_key=unit_key,
            unit_label=unit_label,
            mac_cpe="",
            pppoe_unit=pppoe_unit,
            notes=note,
            image_ap_make=image_ap_make,
            image_ap_sticker_apartment=image_ap_sticker_apartment,
            image_ap_mac=image_ap_mac,
            inventory_mac_verification=inventory_mac_verification,
            implication=implication,
            action=action,
        )

    if pppoe_unit and _canonical_unit_token(pppoe_unit) == unit_key:
        notes = "Good"
    elif pppoe_unit:
        notes = f"PPPoE label maps this CPE to {pppoe_unit}"
        implication = f"PPPoE/inventory mismatch for {unit_label}."
        action = "Verify patching / router placement"
    else:
        notes = "Inventory MAC present"
        implication = "CPE scanned, but PPPoE label could not be derived."
        action = "Verify subscriber label"

    return AuditRow(
        unit_key=unit_key,
        unit_label=unit_label,
        mac_cpe=mac,
        pppoe_unit=pppoe_unit,
        notes=notes,
        image_ap_make=image_ap_make,
        image_ap_sticker_apartment=image_ap_sticker_apartment,
        image_ap_mac=image_ap_mac,
        inventory_mac_verification=inventory_mac_verification,
        implication=implication,
        action=action,
    )


def _build_rows(address_text: str, layout: LayoutSpec) -> list[AuditRow]:
    source_rows = _iter_nycha_rows_for_address(address_text)
    # WHY: The expected unit list is the authoritative pre-build roster. If a building has
    # units in the expected list but not the CSV (e.g. units not yet scanned), we still
    # want them as empty rows so the count is accurate. If CSV has units not in the expected
    # list, we still include them — the expected list supplements, doesn't exclude.
    expected_units = _expected_units_for_address(address_text)

    mapped_by_unit: dict[str, AuditRow] = {}
    for row in source_rows:
        raw_unit = str(row.get("Unit") or "").strip() or _extract_pppoe_unit(row.get("PPPoE"))
        audit_row = _classify_row(row, raw_unit)
        mapped_by_unit[audit_row.unit_key] = audit_row

    output_rows: list[AuditRow] = []
    if layout.donor_units:
        for switch_port, unit_label in layout.donor_units:
            unit_key = _canonical_unit_token(unit_label)
            row = mapped_by_unit.get(unit_key) or AuditRow(
                unit_key=unit_key,
                unit_label=unit_label,
                mac_cpe="",
                pppoe_unit="",
                notes="",
                image_ap_make="",
                image_ap_sticker_apartment="",
                image_ap_mac="",
                inventory_mac_verification="",
                implication="",
                action="",
            )
            row.unit_label = unit_label
            row.switch_port = switch_port
            output_rows.append(row)
        return output_rows

    if expected_units:
        # Build output using the expected unit list as the row order/roster.
        # CSV-matched rows get their data; unmatched expected units become empty rows.
        for unit_label in expected_units:
            unit_key = _canonical_unit_token(unit_label)
            if unit_key in mapped_by_unit:
                row = mapped_by_unit[unit_key]
                row.unit_label = unit_label  # Preserve expected label formatting
                output_rows.append(row)
            else:
                output_rows.append(AuditRow(
                    unit_key=unit_key,
                    unit_label=unit_label,
                    mac_cpe="",
                    pppoe_unit="",
                    notes="NOT INSTALLED",
                    image_ap_make="",
                    image_ap_sticker_apartment="",
                    image_ap_mac="",
                    inventory_mac_verification="",
                    implication="",
                    action="",
                ))
        # Also include any CSV rows not covered by the expected list
        expected_keys = {_canonical_unit_token(u) for u in expected_units}
        for unit_key, row in mapped_by_unit.items():
            if unit_key not in expected_keys:
                output_rows.append(row)
        return output_rows

    if not source_rows:
        raise ValueError(f"No nycha_info rows found for address '{address_text}'.")

    rows = sorted(mapped_by_unit.values(), key=lambda r: (re.sub(r"[^0-9]", "", r.unit_key) or "0", r.unit_key))
    # WHY: Do NOT assign sequential SW1-N ports here. switch_port is populated only from
    # actual bridge evidence (reverse MAC lookup in _apply_live_status). Assigning fake
    # sequential port numbers for unseen units would misrepresent the patching state.
    return rows


def _build_live_context(address_text: str, ops: Any | None) -> LiveContext:
    captured_at_timestamp = datetime.now(timezone.utc).isoformat()
    if ops is None:
        return LiveContext(None, None, {}, {}, 0, 0, None, None, {}, {}, {}, {}, [], captured_at_timestamp=captured_at_timestamp)
    source_rows = _iter_nycha_rows_for_address(address_text)
    inferred_switch_identity = _infer_switch_identity_for_address(ops, source_rows)
    live_port_macs_by_interface = _live_port_macs_for_switch(ops, inferred_switch_identity) if inferred_switch_identity else {}
    controller_verification_by_mac, controller_failures = _build_controller_verification(source_rows)
    live_failures = list(controller_failures)
    resolution = _call_with_timeout("resolve_building_from_address", 8.0, ops._resolve_building_from_address, address_text)
    if not resolution.ok:
        live_failures.append(
            {
                "source": resolution.source,
                "classification": str(resolution.classification or "code_error"),
                "detail": str(resolution.detail or ""),
            }
        )
        switch_identities_by_label_prefix = _map_switch_label_prefixes(None, inferred_switch_identity)
        live_port_macs_by_switch_identity = (
            {inferred_switch_identity: live_port_macs_by_interface}
            if inferred_switch_identity and live_port_macs_by_interface
            else {}
        )
        return LiveContext(
            None,
            None,
            {},
            {},
            0,
            0,
            None,
            inferred_switch_identity,
            live_port_macs_by_interface,
            switch_identities_by_label_prefix,
            live_port_macs_by_switch_identity,
            controller_verification_by_mac,
            live_failures,
            captured_at_timestamp=captured_at_timestamp,
            building_has_db_bridge_hosts=bool(live_port_macs_by_interface),
        )
    best = (resolution.value or {}).get("best_match") or {}
    building_id = str(best.get("prefix") or "").strip() or None
    site_id = (
        str(best.get("site_code") or "").strip()
        or (building_id.split(".", 1)[0] if building_id else None)
    )
    online_units_by_token: dict[str, dict[str, Any]] = {}
    exact_matches_by_unit: dict[str, dict[str, Any]] = {}
    port_observations_by_unit: dict[str, dict[str, Any]] = {}
    auth_observations_by_unit: dict[str, dict[str, Any]] = {}
    dhcp_observations_by_unit: dict[str, dict[str, Any]] = {}
    historical_search_completed: dict[str, bool] = {}
    expected_port_search_completed_by_unit: dict[str, bool] = {}
    switch_scope_search_completed_by_unit: dict[str, bool] = {}
    global_search_completed_by_unit: dict[str, bool] = {}
    active_alert_count = 0
    building_device_count = 0
    site_online_count: int | None = None
    switch_identities_by_label_prefix = _map_switch_label_prefixes(best.get("device_names") or [], inferred_switch_identity)
    live_port_macs_by_switch_identity: dict[str, dict[str, list[str]]] = {}
    _switch_ids = sorted(set(switch_identities_by_label_prefix.values()))
    if len(_switch_ids) <= 1:
        for identity in _switch_ids:
            live_port_macs_by_switch_identity[identity] = _live_port_macs_for_switch(ops, identity)
    else:
        # WHY: Large buildings (e.g. 728 East New York Ave) have 9+ switches. Serial reads at
        # 8s timeout each would take 72s+ minimum, pushing past the 300s per-building limit.
        # Parallel reads keep multi-switch buildings within budget.
        _sw_pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(len(_switch_ids), 6))
        _sw_futures = {_sw_pool.submit(_live_port_macs_for_switch, ops, sw): sw for sw in _switch_ids}
        for _fut, _sw in _sw_futures.items():
            try:
                live_port_macs_by_switch_identity[_sw] = _fut.result(timeout=12)
            except Exception:
                live_port_macs_by_switch_identity[_sw] = {}
                _fut.cancel()
        _sw_pool.shutdown(wait=False, cancel_futures=True)
    if building_id:
        evidence_rows_call = _call_with_timeout(
            "address_inventory_online_unit_evidence",
            3.0,
            ops._address_inventory_online_unit_evidence,
            building_id,
            address_text,
        )
        evidence_rows = evidence_rows_call.value or []
        if not evidence_rows_call.ok:
            live_failures.append(
                {
                    "source": evidence_rows_call.source,
                    "classification": str(evidence_rows_call.classification or "code_error"),
                    "detail": str(evidence_rows_call.detail or ""),
                }
            )
        for row in evidence_rows:
            token = _canonical_unit_token(parse_unit_token(row.get("unit")))
            if token:
                online_units_by_token[token] = row
        exact_rows_call = _call_with_timeout("exact_unit_port_matches", 3.0, ops._exact_unit_port_matches, building_id)
        exact_rows = exact_rows_call.value or []
        if not exact_rows_call.ok:
            live_failures.append(
                {
                    "source": exact_rows_call.source,
                    "classification": str(exact_rows_call.classification or "code_error"),
                    "detail": str(exact_rows_call.detail or ""),
                }
            )
        for row in exact_rows:
            token = _canonical_unit_token(parse_unit_token(row.get("unit")))
            if token:
                exact_matches_by_unit[token] = row
        for source_row in source_rows:
            token = _canonical_unit_token(parse_unit_token(source_row.get("Unit")) or parse_unit_token(source_row.get("PPPoE")) or "")
            if token:
                historical_search_completed[token] = True
                expected_port_search_completed_by_unit[token] = True
                switch_scope_search_completed_by_unit[token] = True
                global_search_completed_by_unit[token] = True
        if site_id:
            # WHY: Serial per-unit calls (port/pppoe/dhcp) at 3s timeout each take
            # O(units × 9s) = 550s+ for a 61-unit building, blowing the 300s per-building
            # limit. Parallelize across units instead.
            def _fetch_unit_diagnostics(source_row: dict) -> tuple[str, dict, list[dict]]:
                token = _canonical_unit_token(parse_unit_token(source_row.get("Unit")) or parse_unit_token(source_row.get("PPPoE")) or "")
                if not token:
                    return "", {}, []
                exact = exact_matches_by_unit.get(token) or {}
                interface = str(exact.get("interface") or "").strip() or None
                switch_identity_u = str(exact.get("switch_identity") or inferred_switch_identity or "").strip() or None
                unit_port_obs: dict = {}
                unit_auth_obs: dict = {}
                unit_dhcp_obs: dict = {}
                unit_failures: list[dict] = []
                if interface and hasattr(ops, "get_port_physical_state"):
                    port_call = _call_with_timeout(
                        "get_port_physical_state", 3.0, ops.get_port_physical_state,
                        interface, None, switch_identity_u,
                    )
                    if port_call.ok and isinstance(port_call.value, dict):
                        unit_port_obs = {key: port_call.value.get(key) for key in (
                            "port_up", "port_speed", "port_duplex", "link_partner_speed",
                            "link_partner_duplex", "rx_errors", "tx_errors", "fcs_errors",
                            "crc_errors", "link_flaps", "link_flaps_window_seconds",
                        )}
                    else:
                        unit_failures.append({"source": "get_port_physical_state",
                            "classification": str(port_call.classification or "missing_runtime"),
                            "detail": str(port_call.detail or (port_call.value or {}).get("error") or f"Port physical read failed for {token}.")})
                if hasattr(ops, "get_pppoe_diagnostics"):
                    pppoe_call = _call_with_timeout(
                        "get_pppoe_diagnostics", 3.0, ops.get_pppoe_diagnostics, token, site_id,
                    )
                    if pppoe_call.ok and isinstance(pppoe_call.value, dict):
                        unit_auth_obs = {key: pppoe_call.value.get(key) for key in (
                            "pppoe_active", "pppoe_failed_attempts_seen",
                            "pppoe_failure_reason", "pppoe_last_attempt_timestamp",
                        )}
                        unit_auth_obs["pppoe_no_attempt_evidence"] = (
                            pppoe_call.value.get("pppoe_active") is False
                            and pppoe_call.value.get("pppoe_failed_attempts_seen") is False
                        )
                        unit_auth_obs["evidence_sources"] = ["pppoe_diagnostics"]
                    else:
                        unit_failures.append({"source": "get_pppoe_diagnostics",
                            "classification": str(pppoe_call.classification or "missing_runtime"),
                            "detail": str(pppoe_call.detail or (pppoe_call.value or {}).get("error") or f"PPPoE diagnostics failed for {token}.")})
                if hasattr(ops, "get_dhcp_behavior"):
                    dhcp_call = _call_with_timeout(
                        "get_dhcp_behavior", 3.0, ops.get_dhcp_behavior,
                        token, site_id, switch_identity_u, interface,
                        source_row.get("MAC Address") or source_row.get("mac"),
                    )
                    if dhcp_call.ok and isinstance(dhcp_call.value, dict):
                        unit_dhcp_obs = {key: dhcp_call.value.get(key) for key in (
                            "dhcp_expected", "dhcp_discovers_seen", "dhcp_offers_seen",
                            "dhcp_offer_source", "dhcp_expected_server", "rogue_dhcp_detected",
                        )}
                        unit_dhcp_obs["evidence_sources"] = ["dhcp_behavior"]
                return token, {"port": unit_port_obs, "auth": unit_auth_obs, "dhcp": unit_dhcp_obs}, unit_failures

            _diag_pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(len(source_rows), 12))
            _diag_futures = {_diag_pool.submit(_fetch_unit_diagnostics, row): row for row in source_rows}
            for _dfut in concurrent.futures.as_completed(_diag_futures):
                try:
                    _tok, _obs, _fails = _dfut.result(timeout=10)
                    if _tok:
                        if _obs.get("port"):
                            port_observations_by_unit[_tok] = _obs["port"]
                        if _obs.get("auth"):
                            auth_observations_by_unit[_tok] = _obs["auth"]
                        if _obs.get("dhcp"):
                            dhcp_observations_by_unit[_tok] = _obs["dhcp"]
                    live_failures.extend(_fails)
                except Exception:
                    pass
            _diag_pool.shutdown(wait=False, cancel_futures=True)
        building_health_call = _call_with_timeout("get_building_health", 3.0, ops.get_building_health, building_id, True)
        building_health = building_health_call.value
        if not building_health_call.ok:
            live_failures.append(
                {
                    "source": building_health_call.source,
                    "classification": str(building_health_call.classification or "code_error"),
                    "detail": str(building_health_call.detail or ""),
                }
            )
        if building_health:
            building_device_count = int(building_health.get("device_count") or 0)
            active_alert_count = len(building_health.get("active_alerts") or [])
    if site_id:
        site_summary_call = _call_with_timeout("get_site_summary", 3.0, ops.get_site_summary, site_id, True)
        site_summary = site_summary_call.value
        if not site_summary_call.ok:
            live_failures.append(
                {
                    "source": site_summary_call.source,
                    "classification": str(site_summary_call.classification or "code_error"),
                    "detail": str(site_summary_call.detail or ""),
                }
            )
        if site_summary:
            site_online_count = int((site_summary.get("online_customers") or {}).get("count") or 0)
            active_alert_count = max(active_alert_count, len(site_summary.get("active_alerts") or []))
    # Check DB scan for any customer bridge-host MACs on this building's switches.
    # WHY: SSH live reads are non-deterministic (can return empty on one call, data on another).
    # The DB scan is a stable historical record — if it found MACs, the switch was reachable
    # and reporting bridge data. Use this to gate "UNPLUGGED / BAD CABLE" vs "CONTROLLER VERIFIED".
    building_has_db_bridge_hosts = False
    if building_id:
        try:
            scan_id = ops.latest_scan_id()
            count = ops.db.execute(
                """
                select count(*) from bridge_hosts bh
                join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                where bh.scan_id=? and d.identity like ? and bh.local=0 and bh.on_interface like 'ether%'
                """,
                (scan_id, f"{building_id}%"),
            ).fetchone()[0]
            building_has_db_bridge_hosts = count > 0
        except Exception:
            pass
    # Also check whether the current live SSH read returned any MACs — either source counts.
    if not building_has_db_bridge_hosts:
        building_has_db_bridge_hosts = any(
            bool(ports) for ports in live_port_macs_by_switch_identity.values()
        ) or bool(live_port_macs_by_interface)
    return LiveContext(
        building_id=building_id,
        site_id=site_id,
        online_units_by_token=online_units_by_token,
        exact_matches_by_unit=exact_matches_by_unit,
        active_alert_count=active_alert_count,
        building_device_count=building_device_count,
        site_online_count=site_online_count,
        inferred_switch_identity=inferred_switch_identity,
        live_port_macs_by_interface=live_port_macs_by_interface,
        switch_identities_by_label_prefix=switch_identities_by_label_prefix,
        live_port_macs_by_switch_identity=live_port_macs_by_switch_identity,
        controller_verification_by_mac=controller_verification_by_mac,
        live_failures=live_failures,
        port_observations_by_unit=port_observations_by_unit,
        auth_observations_by_unit=auth_observations_by_unit,
        dhcp_observations_by_unit=dhcp_observations_by_unit,
        captured_at_timestamp=captured_at_timestamp,
        historical_search_completed=historical_search_completed or None,
        expected_port_search_completed_by_unit=expected_port_search_completed_by_unit or None,
        switch_scope_search_completed_by_unit=switch_scope_search_completed_by_unit or None,
        global_search_completed_by_unit=global_search_completed_by_unit or None,
        building_has_db_bridge_hosts=building_has_db_bridge_hosts,
    )


def _apply_live_status(audit_row: AuditRow, source_row: dict[str, str], live: LiveContext) -> AuditRow:
    unit_token = _canonical_unit_token(parse_unit_token(audit_row.unit_label) or audit_row.unit_key)
    pppoe_unit_token = _canonical_unit_token(audit_row.pppoe_unit)
    expected_mac = norm_mac(source_row.get("MAC Address") or source_row.get("mac") or "")
    controller = live.controller_verification_by_mac.get(expected_mac) or {}
    audit_row.image_ap_make = str(source_row.get("AP Make") or "").strip()

    # Legacy workbook contract: MAC CPE reflects the current CPE MAC evidence when available.
    # mac_live is still kept separately for comparison/debug logic.
    # mac_controller is populated from Vilo snapshot or TAUC export.
    audit_row.mac_cpe = ""

    # Populate controller MAC from the controller verification record.
    ctrl_snap = controller.get("snapshot_row") or {}
    ctrl_mac = norm_mac(
        ctrl_snap.get("device_mac") or ctrl_snap.get("tauc_mac") or ctrl_snap.get("mac") or ""
    )
    if ctrl_mac:
        audit_row.mac_controller = ctrl_mac.upper()

    observed_mac = ""
    observed_match_kind = ""
    observed_interface = _switch_port_to_interface(audit_row.switch_port) if audit_row.switch_port else None
    switch_prefix = _switch_port_prefix(audit_row.switch_port) if audit_row.switch_port else None
    target_switch_identity = (
        live.switch_identities_by_label_prefix.get(switch_prefix or "")
        or live.inferred_switch_identity
    )

    # WHY: Physical-layout rows start with no switch_port. Do a reverse MAC lookup across all
    # live port maps to find which switch/port the expected CPE is currently seen on.
    if not observed_interface and expected_mac:
        for sw_id, port_map in live.live_port_macs_by_switch_identity.items():
            for iface, macs in port_map.items():
                if expected_mac in macs:
                    observed_interface = iface
                    target_switch_identity = sw_id
                    # Derive a label prefix from the switch identity (e.g. "000007.031.SW01" → "SW1")
                    sw_suffix = sw_id.rsplit(".", 1)[-1] if "." in sw_id else sw_id
                    sw_num = "".join(filter(str.isdigit, sw_suffix))
                    audit_row.switch_port = f"SW{sw_num}-{iface.replace('ether', '')}" if sw_num else iface
                    break
            if observed_interface:
                break
        if not observed_interface and expected_mac:
            for iface, macs in live.live_port_macs_by_interface.items():
                for mac in macs:
                    if _known_mac_bug_kind(expected_mac, mac):
                        observed_interface = iface
                        audit_row.switch_port = iface
                        break
                if observed_interface:
                    break

    if observed_interface:
        per_switch = live.live_port_macs_by_switch_identity.get(target_switch_identity or "") or {}
        if target_switch_identity and target_switch_identity in live.live_port_macs_by_switch_identity:
            observed_candidates = per_switch.get(observed_interface) or []
        else:
            observed_candidates = per_switch.get(observed_interface) or live.live_port_macs_by_interface.get(observed_interface) or []
        if observed_candidates:
            if expected_mac and expected_mac in observed_candidates:
                observed_mac = expected_mac
                observed_match_kind = "exact"
            elif expected_mac:
                bug_adjusted = next((mac for mac in observed_candidates if _known_mac_bug_kind(expected_mac, mac)), "")
                if bug_adjusted:
                    observed_mac = bug_adjusted
                    observed_match_kind = str(_known_mac_bug_kind(expected_mac, bug_adjusted) or "")
            else:
                observed_match_kind = ""
            if not observed_mac:
                known_inventory = {
                    norm_mac(row.get("MAC Address") or row.get("mac") or "")
                    for row in load_nycha_info_rows()
                }
                inventory_candidates = [mac for mac in observed_candidates if mac in known_inventory]
                observed_mac = inventory_candidates[0] if inventory_candidates else observed_candidates[0]
                # WHY: If the live MAC on the port matches what the controller (Vilo/TAUC) reports for this
                # unit but differs from the CSV, this is likely a replacement unit. Count it as a match.
                if observed_mac and not observed_match_kind:
                    ctrl_snap = controller.get("snapshot_row") or {}
                    ctrl_mac = norm_mac(
                        ctrl_snap.get("device_mac") or ctrl_snap.get("tauc_mac") or ctrl_snap.get("mac") or ""
                    )
                    if ctrl_mac and ctrl_mac == observed_mac:
                        observed_match_kind = "controller_replacement"
        # mac_live = what is physically seen on the port right now.
        if observed_mac:
            audit_row.mac_live = observed_mac.upper()
            audit_row.mac_cpe = observed_mac.upper()

    if observed_mac:
        observed_unit = ""
        observed_pppoe = ""
        for row in load_nycha_info_rows():
            if norm_mac(row.get("MAC Address") or row.get("mac") or "") == observed_mac:
                observed_unit = _canonical_unit_token(parse_unit_token(row.get("Unit")))
                observed_pppoe = _extract_pppoe_unit(row.get("PPPoE"))
                break
        audit_row.pppoe_unit = observed_pppoe or audit_row.pppoe_unit
        if observed_match_kind == "exact":
            audit_row.inventory_mac_verification = "Match"
        elif observed_match_kind == "first_octet":
            audit_row.inventory_mac_verification = "Bug-adjusted match"
        elif observed_match_kind == "last_octet":
            audit_row.inventory_mac_verification = "LAN-port MAC"
        else:
            audit_row.inventory_mac_verification = "Mismatch"
        if observed_unit and observed_unit != unit_token:
            if pppoe_unit_token and pppoe_unit_token == observed_unit:
                audit_row.notes = "WRONG UNIT"
                audit_row.implication = (
                    f"Live bridge host on {target_switch_identity or 'mapped switch'} {observed_interface} maps to unit {observed_unit}, "
                    f"and the source row PPPoE label also points to {observed_unit} rather than {unit_token}. "
                    "Treat this as an inventory/workbook unit assignment error, not just a misplaced CPE."
                )
                audit_row.action = f"Correct source row unit mapping from {unit_token} to {observed_unit}"
                return audit_row
            audit_row.notes = "MOVE CPE TO CORRECT UNIT"
            audit_row.implication = f"Live bridge host on {target_switch_identity or 'mapped switch'} {observed_interface} maps to unit {observed_unit}, not {unit_token}. Have field move this CPE to the correct unit drop/port."
            if controller.get("status") == "match":
                audit_row.implication += f" Expected device is still present in {controller.get('label').lower()}."
            audit_row.action = f"Move CPE to correct unit ({unit_token})"
            return audit_row
        if observed_match_kind in {"exact", "first_octet", "controller_replacement"} or (observed_unit and observed_unit == unit_token):
            audit_row.notes = "Good"
            if observed_match_kind == "controller_replacement":
                audit_row.implication = (
                    f"Live bridge host on {target_switch_identity or 'mapped switch'} {observed_interface} is {observed_mac.upper()}, "
                    f"which differs from the CSV MAC {expected_mac.upper() if expected_mac else '(none)'} but matches the controller record. "
                    "Likely a replacement unit — controller and live evidence agree."
                )
                audit_row.inventory_mac_verification = "Match"
            else:
                audit_row.implication = f"Live bridge host on {target_switch_identity or 'mapped switch'} {observed_interface} matches the expected unit."
                if observed_match_kind == "first_octet":
                    audit_row.implication += f" Observed live MAC {observed_mac.upper()} is treated as the expected MAC {expected_mac.upper()} because of the known off-by-one MAC bug."
                if controller.get("status") == "match":
                    audit_row.implication += f" {controller.get('label')}."
            audit_row.action = "None"
            return audit_row
        if observed_match_kind == "last_octet":
            audit_row.notes = "MOVE CPE TO WAN PORT"
            audit_row.implication = f"Live bridge host on {target_switch_identity or 'mapped switch'} {observed_interface} is {observed_mac.upper()}, which is one off in the last octet from expected {expected_mac.upper()}. Treat this as the CPE being plugged into the LAN port."
            audit_row.action = "Move CPE to WAN/uplink port"
            return audit_row
        audit_row.notes = "UNKNOWN MAC ON PORT"
        audit_row.implication = f"Live bridge host on {target_switch_identity or 'mapped switch'} {observed_interface} does not map cleanly to a known unit."
        audit_row.action = "Identify device on port"
        return audit_row

    exact = live.exact_matches_by_unit.get(unit_token or "")
    address_online = live.online_units_by_token.get(unit_token or "")
    local_online = find_local_online_cpe_row(
        network_name=source_row.get("PPPoE"),
        mac=source_row.get("MAC Address") or source_row.get("mac"),
        serial=source_row.get("AP Serial Number"),
    )
    mac_expected = expected_mac
    local_mac = norm_mac((local_online or {}).get("mac") or "")

    # WHY: "UNPLUGGED / BAD CABLE" is only valid when we have evidence the switch was reachable
    # and reporting bridge data. live.building_has_db_bridge_hosts combines the stable DB scan
    # result with the current live SSH read — more reliable than a single SSH call alone.
    switch_is_reporting = live.building_has_db_bridge_hosts

    if local_online:
        if switch_is_reporting:
            # Controller confirms device registered and switch is reporting — this unit's MAC is absent, so cable issue.
            audit_row.notes = "UNPLUGGED / BAD CABLE"
            audit_row.implication = "Controller confirms this unit is registered and the switch is actively reporting other MACs, but this unit's MAC is not seen on the port. Device is likely unplugged or has a bad cable."
            audit_row.action = "Check cable / plug in CPE"
        else:
            audit_row.notes = "CONTROLLER VERIFIED"
            audit_row.implication = "Controller confirms this unit is registered, but the switch returned no bridge data so Jake cannot confirm port status."
            audit_row.action = "Check switch port / patching"
        audit_row.inventory_mac_verification = ("Match" if local_mac == mac_expected else "Mismatch") if (local_mac and mac_expected) else ""
        if local_mac and not audit_row.mac_controller:
            audit_row.mac_controller = local_mac.upper()
        return audit_row

    if address_online:
        sources = ", ".join(address_online.get("sources") or address_online.get("evidence_sources") or [])
        if switch_is_reporting:
            audit_row.notes = "UNPLUGGED / BAD CABLE"
            audit_row.implication = f"Router/controller evidence confirms this unit ({sources}) and the switch is reporting other MACs, but this unit is not seen on the port. Device is likely unplugged or has a bad cable."
            audit_row.action = "Check cable / plug in CPE"
        else:
            audit_row.notes = "CONTROLLER VERIFIED"
            audit_row.implication = f"Router/controller evidence confirms this unit ({sources}), but the switch returned no bridge data so Jake cannot confirm port status."
            audit_row.action = "Check switch port / patching"
        audit_row.inventory_mac_verification = "Match" if mac_expected else ""
        return audit_row

    if exact and controller.get("status") == "match":
        switch_identity = str(exact.get("switch_identity") or "").strip()
        interface = str(exact.get("interface") or "").strip()
        if switch_is_reporting:
            audit_row.notes = "UNPLUGGED / BAD CABLE"
            audit_row.implication = f"Prior access mapping says {switch_identity} {interface} and {controller.get('label').lower()} matches, but this unit's MAC is not seen on that port. Device is likely unplugged or has a bad cable."
            audit_row.action = "Check cable / plug in CPE"
        else:
            audit_row.notes = "CONTROLLER VERIFIED"
            audit_row.implication = f"Prior access mapping says {switch_identity} {interface} and {controller.get('label').lower()} matches, but the switch returned no bridge data so Jake cannot confirm port status."
            audit_row.action = "Check switch port / patching"
        audit_row.inventory_mac_verification = "Match" if mac_expected else ""
        return audit_row

    if controller.get("status") == "match":
        if switch_is_reporting:
            audit_row.notes = "UNPLUGGED / BAD CABLE"
            audit_row.implication = f"{controller.get('label')} matches the expected unit and the switch is reporting other MACs, but this unit's MAC is not seen. Device is likely unplugged or has a bad cable."
            audit_row.action = "Check cable / plug in CPE"
        else:
            audit_row.notes = "CONTROLLER VERIFIED"
            audit_row.implication = f"{controller.get('label')} matches the expected unit, but Jake has no live bridge-host evidence — the switch returned no bridge data."
            audit_row.action = "Check switch port / patching"
        audit_row.inventory_mac_verification = "Match"
        return audit_row

    if controller.get("status") == "mismatch":
        # WHY: Controller mismatch alone cannot populate MAC CPE because stale or wrong inventory does not prove what is physically live on the edge port.
        audit_row.notes = "CONTROLLER MISMATCH"
        audit_row.implication = f"{controller.get('label')} for the expected MAC does not line up cleanly with the expected unit."
        audit_row.action = "Check controller inventory and labeling"
        audit_row.inventory_mac_verification = "Mismatch"
        return audit_row

    if live.live_failures:
        failures = "; ".join(
            f"{row['source']}={row['classification']}" + (f" ({row['detail']})" if row.get("detail") else "")
            for row in live.live_failures
        )
        audit_row.notes = "LIVE LOOKUP FAILED"
        audit_row.implication = f"Jake could not complete live audit evidence collection: {failures}."
        audit_row.action = "Retry live evidence collection / inspect runtime dependencies"
        return audit_row

    if live.active_alert_count:
        audit_row.notes = "NO LIVE EVIDENCE"
        audit_row.implication = f"No current bridge-host or controller confirmation for this unit. Site/building currently has {live.active_alert_count} active alerts."
        audit_row.action = "Check current site/building fault domain"
        return audit_row

    audit_row.notes = "NOT INSTALLED"
    audit_row.implication = "No current bridge-host or controller evidence for this unit."
    audit_row.action = "Verify install status"
    return audit_row


def _apply_diagnosis_status(audit_row: AuditRow, source_row: dict[str, str], live: LiveContext) -> AuditRow:
    result = build_workbook_diagnosis_result(audit_row, source_row, live)
    diagnosis = result.diagnosis
    audit_row.diagnosis_status = diagnosis.primary_status
    audit_row.diagnosis_confidence = diagnosis.confidence
    audit_row.diagnosis_explanation = diagnosis.explanation
    audit_row.notes = result.workbook_status
    audit_row.inventory_mac_verification = result.workbook_verification
    if result.workbook_action:
        audit_row.action = result.workbook_action
    audit_row.implication = result.evidence_summary
    return audit_row


def _capture_diagnosis_debug(audit_row: AuditRow, source_row: dict[str, str], live: LiveContext):
    result = build_workbook_diagnosis_result(audit_row, source_row, live)
    diagnosis = result.diagnosis
    audit_row.diagnosis_status = diagnosis.primary_status
    audit_row.diagnosis_confidence = diagnosis.confidence
    audit_row.diagnosis_explanation = diagnosis.explanation
    audit_row.diagnosis_dispatch_required = diagnosis.dispatch_required
    audit_row.diagnosis_dispatch_priority = diagnosis.dispatch_priority
    audit_row.diagnosis_backend_action = result.backend_action or ""
    audit_row.diagnosis_field_action = result.field_action or ""
    audit_row.reality_contradictions_count = len(result.reality.contradictions)
    audit_row.reality_unknowns_count = len(result.reality.unknowns)
    audit_row.evidence_unknowns = list(result.reality.unknowns)
    audit_row.evidence_unknowns_summary = "; ".join(result.reality.unknowns)
    audit_row.evidence_contradictions = list(result.reality.contradictions)
    audit_row.evidence_contradictions_summary = "; ".join(result.reality.contradictions)
    audit_row.evidence_stale_sources = list(result.reality.stale_data_sources)
    audit_row.evidence_stale_sources_summary = "; ".join(result.reality.stale_data_sources)
    return result


def compare_legacy_vs_diagnosis(audit_row: AuditRow, result=None) -> dict[str, Any]:
    legacy_status = str(audit_row.legacy_status or audit_row.notes or "").strip()
    diagnosis = getattr(result, "diagnosis", None)
    reality = getattr(result, "reality", None)
    diagnosis_status = str(
        getattr(diagnosis, "primary_status", None) or audit_row.diagnosis_status or ""
    ).strip() or "UNKNOWN"
    diagnosis_confidence = str(
        getattr(diagnosis, "confidence", None) or audit_row.diagnosis_confidence or ""
    ).strip() or "low"
    diagnosis_dispatch_required = getattr(diagnosis, "dispatch_required", audit_row.diagnosis_dispatch_required)
    diagnosis_dispatch_priority = str(
        getattr(diagnosis, "dispatch_priority", None) or audit_row.diagnosis_dispatch_priority or ""
    ).strip() or "none"
    contradictions = list(getattr(reality, "contradictions", []) or [])
    unknowns_count = len(getattr(reality, "unknowns", []) or [])
    if reality is None:
        contradictions = list(audit_row.evidence_contradictions or [])
        unknowns_count = int(audit_row.reality_unknowns_count or 0)
    blocking_contradictions, non_blocking_diagnostic_signals = _split_contradictions(contradictions)
    contradictions_count = len(contradictions)
    match = legacy_status.upper() == diagnosis_status.upper() or (
        legacy_status == "Good" and diagnosis_status == "HEALTHY"
    )
    severity = "low"
    reason = "Legacy and diagnosis are aligned."
    category = "aligned"

    legacy_field_issue = legacy_status.upper() in {
        "UNPLUGGED / BAD CABLE",
        "MOVE CPE TO CORRECT UNIT",
        "MOVE CPE TO WAN PORT",
        "UNKNOWN MAC ON PORT",
    }
    diagnosis_backend_first = diagnosis_status in {
        "CONTROLLER_MAPPING_MISMATCH",
        "PPPoE_AUTH_FAILURE",
        "INVENTORY_MAC_MISMATCH",
        "CONTROLLER_STALE_DEVICE",
        "DHCP_NO_OFFER",
        "DHCP_ROGUE_OR_WRONG_SERVER",
    }
    if not match:
        reason = f"Legacy `{legacy_status}` differs from diagnosis `{diagnosis_status}`."
        if legacy_status.upper() == "UNPLUGGED / BAD CABLE" and str(audit_row.mac_live or "").strip():
            severity = "high"
            reason = "Legacy says unplugged/bad cable even though a live MAC is present."
            category = "legacy_unplugged_but_mac_live"
        elif legacy_status.upper() in {"MOVE CPE TO CORRECT UNIT", "WRONG UNIT"} and diagnosis_status in {"DEVICE_SWAPPED_OR_WRONG_UNIT", "INVENTORY_MAC_MISMATCH"}:
            severity = "low"
            reason = "Legacy and diagnosis both point to a unit/device identity problem with different wording."
            category = "wording_only_identity_difference"
        elif legacy_field_issue and diagnosis_backend_first:
            severity = "high"
            reason = "Legacy points to a field issue, but diagnosis points to a backend-fixable issue."
            category = "legacy_field_issue_vs_backend_issue"
        elif legacy_field_issue and diagnosis_dispatch_required is False:
            severity = "high"
            reason = "Legacy would likely trigger dispatch, but diagnosis says dispatch is not required."
            category = "legacy_dispatch_vs_no_dispatch"
        elif legacy_status.upper() == "CONTROLLER MISMATCH" and diagnosis_status == "DEVICE_SWAPPED_OR_WRONG_UNIT":
            severity = "high"
            reason = "Legacy blames controller mismatch while diagnosis points to a swapped device or wrong-unit path."
            category = "legacy_controller_vs_device_swap"
        elif legacy_status.upper() == "LIVE LOOKUP FAILED" and diagnosis_status in {"DEVICE_SWAPPED_OR_WRONG_UNIT", "INVENTORY_MAC_MISMATCH"}:
            severity = "high"
            reason = "Legacy collapses the row to lookup failure while diagnosis still found a concrete inventory/patch issue."
            category = "legacy_lookup_failed_but_diagnosis_found_cause"
        elif legacy_status.upper() == "UNPLUGGED / BAD CABLE" and diagnosis_status in {"L2_PRESENT_NO_SERVICE", "PPPoE_NO_ATTEMPT"}:
            severity = "high"
            reason = "Legacy says unplugged, but diagnosis keeps the issue in the service/config domain."
            category = "legacy_unplugged_vs_service_domain"
        elif legacy_status.upper() == "CONTROLLER MISMATCH" and diagnosis_status == "INVENTORY_MAC_MISMATCH":
            severity = "medium"
            reason = "Both paths found an identity problem, but diagnosis attributes it to inventory/live MAC mismatch."
            category = "controller_vs_inventory_mismatch"
        else:
            severity = "medium"
            category = "classification_difference"
    return {
        "unit": audit_row.unit_label,
        "legacy_status": legacy_status,
        "diagnosis_primary_status": diagnosis_status,
        "diagnosis_status": diagnosis_status,
        "diagnosis_confidence": diagnosis_confidence,
        "diagnosis_dispatch_required": diagnosis_dispatch_required,
        "diagnosis_dispatch_priority": diagnosis_dispatch_priority,
        "reality_contradictions_count": contradictions_count,
        "blocking_contradictions_count": len(blocking_contradictions),
        "non_blocking_diagnostic_signals_count": len(non_blocking_diagnostic_signals),
        "reality_unknowns_count": unknowns_count,
        "override_applied": audit_row.override_applied,
        "override_reason": audit_row.override_reason,
        "match": match,
        "severity": severity,
        "category": category,
        "reason": reason,
    }


def _apply_workbook_diagnosis_override(audit_row: AuditRow, result, override_reason: str) -> AuditRow:
    audit_row.override_applied = True
    audit_row.override_reason = override_reason
    audit_row.override_confidence = result.confidence
    audit_row.notes = result.workbook_status
    audit_row.inventory_mac_verification = result.workbook_verification
    if result.workbook_action:
        audit_row.action = result.workbook_action
    audit_row.implication = result.evidence_summary
    return audit_row


def _apply_workbook_diagnosis_rendering(audit_row: AuditRow, result) -> AuditRow:
    rendered = replace(audit_row)
    rendered.notes = result.workbook_status
    rendered.inventory_mac_verification = result.workbook_verification
    if result.workbook_action:
        rendered.action = result.workbook_action
    rendered.implication = result.evidence_summary
    return rendered


def _has_strong_device_swap_evidence(result) -> bool:
    evidence = result.evidence
    expected_mac = str(evidence.inventory_truth.expected_mac or "").strip().lower()
    live_mac = str(evidence.l2_truth.live_mac or "").strip().lower()
    if not expected_mac or not live_mac or expected_mac == live_mac:
        return False
    if evidence.l2_truth.any_mac_on_expected_port is not True:
        return False
    if evidence.l2_truth.expected_mac_seen is True and evidence.l2_truth.live_port == evidence.inventory_truth.expected_port:
        return False
    return True


def _has_strong_service_domain_evidence(result) -> bool:
    evidence = result.evidence
    diagnosis = result.diagnosis
    if evidence.l2_truth.live_mac_seen is not True:
        return False
    if evidence.auth_truth.pppoe_active is True:
        return False
    if diagnosis.primary_status not in {"L2_PRESENT_NO_SERVICE", "PPPoE_NO_ATTEMPT"}:
        return False
    if evidence.auth_truth.pppoe_failed_attempts_seen is True or evidence.auth_truth.pppoe_failures:
        return False
    return True


def _has_strong_lookup_failed_evidence(result) -> bool:
    evidence = result.evidence
    return evidence.l2_truth.live_mac_seen is True or evidence.controller_truth.controller_seen is True


def _has_blocking_contradictions(result) -> bool:
    return any(
        is_blocking_contradiction(contradiction)
        for contradiction in list(getattr(result.reality, "contradictions", []) or [])
    )


def is_blocking_contradiction(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    if normalized.startswith("hard:") or normalized.startswith("blocking:"):
        return True
    if "controller" in normalized and "online" in normalized and "no" in normalized and "mac" in normalized:
        return True
    if "pppoe is active" in normalized and ("wrong device" in normalized or "wrong unit" in normalized):
        return True
    if "pppoe is active" in normalized and "controller reports the device offline" in normalized:
        return True
    if "dhcp offers" in normalized and "unexpected server" in normalized:
        return True
    if "mac is present at l2" in normalized and "no pppoe attempt is visible" in normalized:
        return False
    if "controller" in normalized and "stale" in normalized and "live" in normalized:
        return False
    if "historical mac" in normalized and "device_swapped_or_wrong_unit" in normalized:
        return False
    return False


def _split_contradictions(contradictions: list[str] | None) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    non_blocking: list[str] = []
    for contradiction in list(contradictions or []):
        if is_blocking_contradiction(contradiction):
            blocking.append(contradiction)
        else:
            non_blocking.append(contradiction)
    return blocking, non_blocking


def _unknowns_block_override(result, category: str, confidence: str) -> bool:
    unknown_count = len(getattr(result.reality, "unknowns", []) or [])
    if unknown_count < 3:
        return False
    explicitly_allowed = {
        "legacy_unplugged_but_mac_live",
        "legacy_field_issue_vs_backend_issue",
        "legacy_dispatch_vs_no_dispatch",
        "legacy_unplugged_vs_service_domain",
        "legacy_lookup_failed_but_diagnosis_found_cause",
        "legacy_controller_vs_device_swap",
    }
    return not (category in explicitly_allowed and confidence == "high")


def _should_apply_diagnosis_override(audit_row: AuditRow, comparison: dict[str, Any], result) -> tuple[bool, str]:
    if comparison.get("severity") != "high":
        return False, ""
    if str(result.diagnosis.primary_status or "").strip() == "NEEDS_MORE_EVIDENCE":
        return False, ""

    category = str(comparison.get("category") or "")
    medium_or_high_categories = {
        "legacy_unplugged_but_mac_live",
        "legacy_field_issue_vs_backend_issue",
        "legacy_dispatch_vs_no_dispatch",
    }
    high_only_categories = {
        "legacy_unplugged_vs_service_domain",
        "legacy_lookup_failed_but_diagnosis_found_cause",
        "legacy_controller_vs_device_swap",
    }
    confidence = str(result.diagnosis.confidence or "").strip().lower()
    if _has_blocking_contradictions(result):
        return False, ""
    if _unknowns_block_override(result, category, confidence):
        return False, ""
    if category in medium_or_high_categories:
        if confidence not in {"high", "medium"}:
            return False, ""
        if category == "legacy_unplugged_but_mac_live" and result.evidence.l2_truth.live_mac_seen is not True:
            return False, ""
        return True, str(comparison.get("reason") or "Diagnosis override applied for a high-severity legacy mismatch.")
    if category in high_only_categories:
        if confidence != "high":
            return False, ""
        if category == "legacy_controller_vs_device_swap" and not _has_strong_device_swap_evidence(result):
            return False, ""
        if category == "legacy_unplugged_vs_service_domain" and not _has_strong_service_domain_evidence(result):
            return False, ""
        if category == "legacy_lookup_failed_but_diagnosis_found_cause" and not _has_strong_lookup_failed_evidence(result):
            return False, ""
        return True, str(comparison.get("reason") or "Diagnosis override applied for a high-severity legacy mismatch.")
    return False, ""


def _maybe_apply_diagnosis_override(audit_row: AuditRow, result, *, mutate_rendering: bool = True) -> AuditRow:
    comparison = compare_legacy_vs_diagnosis(audit_row, result)
    should_apply, reason = _should_apply_diagnosis_override(audit_row, comparison, result)
    if should_apply:
        audit_row.override_applied = True
        audit_row.override_reason = reason
        audit_row.override_confidence = result.confidence
        if mutate_rendering:
            _apply_workbook_diagnosis_override(audit_row, result, reason)
    return audit_row


def _assess_cutover_safety(audit_row: AuditRow, comparison: dict[str, Any]) -> tuple[bool, str]:
    confidence = str(comparison.get("diagnosis_confidence") or "").strip().lower()
    status = str(comparison.get("diagnosis_primary_status") or comparison.get("diagnosis_status") or "").strip()
    blocking_contradictions = int(comparison.get("blocking_contradictions_count") or 0)
    unknowns = int(comparison.get("reality_unknowns_count") or 0)
    severity = str(comparison.get("severity") or "").strip().lower()
    override_applied = bool(comparison.get("override_applied"))

    if status == "NEEDS_MORE_EVIDENCE":
        return False, "Diagnosis still needs more evidence."
    if confidence not in {"high", "medium"}:
        return False, "Diagnosis confidence is too low for cutover."
    if blocking_contradictions > 0:
        return False, "Reality model contains blocking contradictions."
    if unknowns >= 3:
        return False, "Reality model is too unknown-heavy."
    if severity == "high" and not override_applied:
        return False, "High-severity legacy mismatch remains unresolved."
    return True, ""


def generate_workbook_comparison_report(rows: list[AuditRow]) -> dict[str, Any]:
    comparisons = [compare_legacy_vs_diagnosis(row) for row in rows if str(row.legacy_status or row.notes or "").strip()]
    matches = [row for row in comparisons if row["match"]]
    mismatches = [row for row in comparisons if not row["match"]]
    by_severity = {
        "high": [row for row in mismatches if row["severity"] == "high"],
        "medium": [row for row in mismatches if row["severity"] == "medium"],
        "low": [row for row in mismatches if row["severity"] == "low"],
    }
    categories: dict[str, int] = {}
    for row in mismatches:
        key = f"{row['legacy_status']} -> {row['diagnosis_status']}"
        categories[key] = categories.get(key, 0) + 1
    top_categories = [
        {"category": key, "count": count}
        for key, count in sorted(categories.items(), key=lambda item: (-item[1], item[0]))
    ]
    high_severity_examples = by_severity["high"][:10]
    overridden_rows = [row for row in rows if row.override_applied]
    remaining_high_severity = [
        row for row in comparisons
        if row["severity"] == "high"
        and not any(audit_row.unit_label == row["unit"] and audit_row.override_applied for audit_row in rows)
    ]
    overrides_by_category: dict[str, int] = {}
    for row in overridden_rows:
        comparison = compare_legacy_vs_diagnosis(row)
        key = str(comparison.get("category") or "override")
        overrides_by_category[key] = overrides_by_category.get(key, 0) + 1
    return {
        "total_rows": len(comparisons),
        "matches": len(matches),
        "mismatches": len(mismatches),
        "high_severity_mismatches": len(by_severity["high"]),
        "medium_severity_mismatches": len(by_severity["medium"]),
        "low_severity_mismatches": len(by_severity["low"]),
        "top_mismatch_categories": top_categories[:10],
        "high_severity_examples": high_severity_examples,
        "remaining_high_severity_mismatches": len(remaining_high_severity),
        "overrides_applied_count": len(overridden_rows),
        "overrides_by_category": [
            {"category": key, "count": count}
            for key, count in sorted(overrides_by_category.items(), key=lambda item: (-item[1], item[0]))
        ],
        "sample_override_rows": [
            {
                "unit": row.unit_label,
                "legacy_status": row.legacy_status,
                "diagnosis_status": row.diagnosis_status,
                "override_reason": row.override_reason,
            }
            for row in overridden_rows[:10]
        ],
        "comparisons": comparisons,
    }


def generate_workbook_cutover_report(rows: list[AuditRow]) -> dict[str, Any]:
    comparisons = [compare_legacy_vs_diagnosis(row) for row in rows if str(row.legacy_status or row.notes or "").strip()]
    legacy_status_counts: dict[str, int] = {}
    diagnosis_status_counts: dict[str, int] = {}
    rows_safe = 0
    rows_blocked = 0
    needs_more_evidence_count = 0
    unknown_heavy_count = 0
    contradiction_count = 0
    blocking_contradictions_count = 0
    non_blocking_diagnostic_signals_count = 0

    for row, comparison in zip(
        [r for r in rows if str(r.legacy_status or r.notes or "").strip()],
        comparisons,
        strict=False,
    ):
        legacy_key = str(comparison.get("legacy_status") or "UNKNOWN")
        diagnosis_key = str(comparison.get("diagnosis_primary_status") or comparison.get("diagnosis_status") or "UNKNOWN")
        legacy_status_counts[legacy_key] = legacy_status_counts.get(legacy_key, 0) + 1
        diagnosis_status_counts[diagnosis_key] = diagnosis_status_counts.get(diagnosis_key, 0) + 1
        if diagnosis_key == "NEEDS_MORE_EVIDENCE":
            needs_more_evidence_count += 1
        if int(comparison.get("reality_unknowns_count") or 0) >= 3:
            unknown_heavy_count += 1
        if int(comparison.get("reality_contradictions_count") or 0) > 0:
            contradiction_count += 1
        if int(comparison.get("blocking_contradictions_count") or 0) > 0:
            blocking_contradictions_count += 1
        if int(comparison.get("non_blocking_diagnostic_signals_count") or 0) > 0:
            non_blocking_diagnostic_signals_count += 1
        safe, reason = _assess_cutover_safety(row, comparison)
        row.cutover_safe = safe
        row.cutover_block_reason = reason
        if safe:
            rows_safe += 1
        else:
            rows_blocked += 1

    exact_matches = sum(1 for row in comparisons if row["match"])
    mismatches = sum(1 for row in comparisons if not row["match"])
    high = sum(1 for row in comparisons if row["severity"] == "high")
    medium = sum(1 for row in comparisons if row["severity"] == "medium")
    low = sum(1 for row in comparisons if row["severity"] == "low")
    overrides_applied_count = sum(1 for row in rows if row.override_applied)
    remaining_high = sum(
        1 for row in comparisons if row["severity"] == "high" and not row["override_applied"]
    )

    return {
        "total_rows": len(comparisons),
        "legacy_status_counts": legacy_status_counts,
        "diagnosis_status_counts": diagnosis_status_counts,
        "exact_matches": exact_matches,
        "mismatches": mismatches,
        "high_severity_mismatches": high,
        "medium_severity_mismatches": medium,
        "low_severity_mismatches": low,
        "overrides_applied_count": overrides_applied_count,
        "remaining_high_severity_mismatches": remaining_high,
        "needs_more_evidence_count": needs_more_evidence_count,
        "unknown_heavy_count": unknown_heavy_count,
        "contradiction_count": contradiction_count,
        "blocking_contradictions_count": blocking_contradictions_count,
        "non_blocking_diagnostic_signals_count": non_blocking_diagnostic_signals_count,
        "rows_safe_for_cutover": rows_safe,
        "rows_blocked_from_cutover": rows_blocked,
    }


def generate_workbook_evidence_gap_report(rows: list[AuditRow]) -> dict[str, Any]:
    relevant_rows = [row for row in rows if str(row.legacy_status or row.notes or "").strip()]
    unknown_distribution: dict[int, int] = {}
    top_unknown_fields: dict[str, int] = {}
    rows_missing_l1 = 0
    rows_missing_pppoe = 0
    rows_missing_dhcp = 0
    rows_missing_controller_freshness = 0
    rows_missing_global_mac_search = 0
    rows_missing_historical_mac_search = 0

    for row in relevant_rows:
        unknowns = list(row.evidence_unknowns or [])
        unknown_count = len(unknowns)
        unknown_distribution[unknown_count] = unknown_distribution.get(unknown_count, 0) + 1
        for item in unknowns:
            key = str(item or "").split(":", 1)[0].strip()
            if key:
                top_unknown_fields[key] = top_unknown_fields.get(key, 0) + 1
        if any(item.startswith("physical_truth.port_up") or item.startswith("physical_truth.port_speed") for item in unknowns):
            rows_missing_l1 += 1
        if any(item.startswith("auth_truth.pppoe_logs") for item in unknowns):
            rows_missing_pppoe += 1
        if any(item.startswith("dhcp_truth.") for item in unknowns):
            rows_missing_dhcp += 1
        if any(
            item.startswith("controller_truth.controller_last_seen")
            or item.startswith("controller_truth.controller_snapshot")
            for item in unknowns
        ) or any("controller_truth." in stale for stale in list(row.evidence_stale_sources or [])):
            rows_missing_controller_freshness += 1
        if any(item.startswith("l2_truth.global_search") for item in unknowns):
            rows_missing_global_mac_search += 1
        if any(item.startswith("l2_truth.historical_search") for item in unknowns):
            rows_missing_historical_mac_search += 1

    recommendations: list[str] = []
    if rows_missing_l1:
        recommendations.append("Improve MikroTik L1 collectors for port state, negotiated speed, and error counters.")
    if rows_missing_pppoe:
        recommendations.append("Improve PPPoE diagnostics collection so no-attempt vs failure is explicit per unit.")
    if rows_missing_dhcp:
        recommendations.append("Improve DHCP observation collection for discover/offer visibility and expected server identity.")
    if rows_missing_controller_freshness:
        recommendations.append("Improve controller freshness capture with reliable last-seen timestamps and snapshot age.")
    if rows_missing_global_mac_search:
        recommendations.append("Record explicit global MAC search completion in workbook-fed evidence.")
    if rows_missing_historical_mac_search:
        recommendations.append("Record explicit historical MAC search completion in workbook-fed evidence.")

    top_unknowns_sorted = [
        {"field": key, "count": count}
        for key, count in sorted(top_unknown_fields.items(), key=lambda item: (-item[1], item[0]))
    ]
    unknown_distribution_sorted = [
        {"unknown_count": key, "rows": count}
        for key, count in sorted(unknown_distribution.items(), key=lambda item: item[0])
    ]

    return {
        "total_rows": len(relevant_rows),
        "unknown_count_distribution": unknown_distribution_sorted,
        "top_unknown_fields": top_unknowns_sorted[:10],
        "rows_missing_l1": rows_missing_l1,
        "rows_missing_pppoe": rows_missing_pppoe,
        "rows_missing_dhcp": rows_missing_dhcp,
        "rows_missing_controller_freshness": rows_missing_controller_freshness,
        "rows_missing_global_mac_search": rows_missing_global_mac_search,
        "rows_missing_historical_mac_search": rows_missing_historical_mac_search,
        "recommended_collector_improvements": recommendations,
    }


def generate_workbook_blocker_report(rows: list[AuditRow]) -> dict[str, Any]:
    relevant_rows = [row for row in rows if str(row.legacy_status or row.notes or "").strip()]
    blocked_rows = [row for row in relevant_rows if not row.cutover_safe]
    blocked_by_status: dict[str, int] = {}
    blocked_by_reason: dict[str, int] = {}
    needs_more_evidence_rows: list[dict[str, Any]] = []
    unresolved_high_severity_rows: list[dict[str, Any]] = []
    per_row_blockers: list[dict[str, Any]] = []
    blocking_contradictions_count = 0
    non_blocking_diagnostic_signals_count = 0

    for row in blocked_rows:
        comparison = compare_legacy_vs_diagnosis(row)
        status = str(comparison.get("diagnosis_primary_status") or comparison.get("diagnosis_status") or "UNKNOWN")
        reason = str(row.cutover_block_reason or "Unknown blocker")
        blocking_contradictions, non_blocking_diagnostic_signals = _split_contradictions(list(row.evidence_contradictions or []))
        blocked_by_status[status] = blocked_by_status.get(status, 0) + 1
        blocked_by_reason[reason] = blocked_by_reason.get(reason, 0) + 1
        blocking_contradictions_count += len(blocking_contradictions)
        non_blocking_diagnostic_signals_count += len(non_blocking_diagnostic_signals)
        item = {
            "unit": row.unit_label,
            "legacy_status": str(row.legacy_status or row.notes or ""),
            "diagnosis_status": status,
            "confidence": str(comparison.get("diagnosis_confidence") or row.diagnosis_confidence or ""),
            "contradictions": list(row.evidence_contradictions or []),
            "blocking_contradictions": blocking_contradictions,
            "non_blocking_diagnostic_signals": non_blocking_diagnostic_signals,
            "unknowns": list(row.evidence_unknowns or []),
            "comparison_category": str(comparison.get("category") or ""),
            "cutover_block_reason": reason,
            "next_best_check": str(row.diagnosis_backend_action or row.diagnosis_field_action or row.action or ""),
        }
        per_row_blockers.append(item)
        if status == "NEEDS_MORE_EVIDENCE":
            needs_more_evidence_rows.append(item)
        if str(comparison.get("severity") or "") == "high" and not row.override_applied:
            unresolved_high_severity_rows.append(item)

    return {
        "total_blocked_rows": len(blocked_rows),
        "blocked_by_status": blocked_by_status,
        "blocked_by_reason": blocked_by_reason,
        "needs_more_evidence_rows": needs_more_evidence_rows,
        "unresolved_high_severity_rows": unresolved_high_severity_rows,
        "blocking_contradictions_count": blocking_contradictions_count,
        "non_blocking_diagnostic_signals_count": non_blocking_diagnostic_signals_count,
        "per_row_blockers": per_row_blockers,
    }


def _evaluate_rows_with_results(
    address_text: str,
    layout: LayoutSpec,
    live: LiveContext,
    *,
    render_diagnosis: bool = False,
) -> tuple[list[AuditRow], dict[str, Any]]:
    rows = _build_rows(address_text, layout)
    diagnosis_results_by_unit: dict[str, Any] = {}
    source_by_unit = {
        (_canonical_unit_token(parse_unit_token(row.get("Unit")) or parse_unit_token(row.get("PPPoE")) or "")): row
        for row in _iter_nycha_rows_for_address(address_text)
    }
    for row in rows:
        source_row = source_by_unit.get(_canonical_unit_token(parse_unit_token(row.unit_label) or row.unit_key))
        if source_row:
            if USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK:
                _apply_diagnosis_status(row, source_row, live)
                if (
                    CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK
                    or USE_DIAGNOSIS_OVERRIDE_FOR_HIGH_SEVERITY
                    or render_diagnosis
                ):
                    diagnosis_results_by_unit[row.unit_label] = build_workbook_diagnosis_result(row, source_row, live)
            else:
                _apply_live_status(row, source_row, live)
                row.legacy_status = row.notes
                diagnosis_result = None
                if (
                    CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK
                    or USE_DIAGNOSIS_OVERRIDE_FOR_HIGH_SEVERITY
                    or render_diagnosis
                ):
                    diagnosis_result = _capture_diagnosis_debug(row, source_row, live)
                    diagnosis_results_by_unit[row.unit_label] = diagnosis_result
                if USE_DIAGNOSIS_OVERRIDE_FOR_HIGH_SEVERITY and diagnosis_result is not None:
                    _maybe_apply_diagnosis_override(
                        row,
                        diagnosis_result,
                        mutate_rendering=USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING,
                    )
    return rows, diagnosis_results_by_unit


def _evaluate_rows(
    address_text: str,
    layout: LayoutSpec,
    live: LiveContext,
) -> list[AuditRow]:
    rows, _ = _evaluate_rows_with_results(address_text, layout, live)
    return rows


def _row_state(audit_row: AuditRow) -> str:
    note = str(audit_row.notes or "").strip().upper()
    if note in {"GOOD", "LIVE ONLINE", "LIVE ONLINE VIA ROUTER EVIDENCE"}:
        return "green"
    if note in {"WRONG UNIT", "MOVE CPE TO CORRECT UNIT", "MOVE CPE TO WAN PORT",
                "UNKNOWN MAC ON PORT", "UNPLUGGED / BAD CABLE"}:
        return "yellow"
    if note.startswith("PPPOE LABEL MAPS THIS CPE TO"):
        return "yellow"
    return "red"


def _weighted_ready_score(rows: list[AuditRow]) -> int:
    """Verified readiness: only green rows count as ready; yellow/red count as not ready."""
    if not rows:
        return 0
    green = sum(1 for row in rows if _row_state(row) == "green")
    return round((green / len(rows)) * 100)


def _apply_base_formatting(ws, layout: LayoutSpec, address_text: str, rows: list[AuditRow]) -> None:
    xl = _require_openpyxl()
    Alignment = xl["Alignment"]
    Font = xl["Font"]
    PatternFill = xl["PatternFill"]
    ws.title = _sheet_title_for_address(address_text)
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    good_fill = PatternFill("solid", fgColor="C6EFCE")
    seen_fill = PatternFill("solid", fgColor="FFF2CC")
    warn_fill = PatternFill("solid", fgColor="FCE4D6")
    bold = Font(bold=True)

    title_cols = layout.title_columns
    ws[f"{title_cols[0]}1"] = "NOT INSTALLED"
    ws[f"{title_cols[1]}1"] = "Good"
    ws[f"{title_cols[2]}1"] = "Seen/Wrong"
    ws[f"{title_cols[3]}1"] = f"{_weighted_ready_score(rows)}% Verified Ready"
    ws[f"{title_cols[0]}1"].fill = warn_fill
    ws[f"{title_cols[1]}1"].fill = good_fill
    ws[f"{title_cols[2]}1"].fill = seen_fill
    for cell in (f"{title_cols[0]}1", f"{title_cols[1]}1", f"{title_cols[2]}1", f"{title_cols[3]}1"):
        ws[cell].font = bold

    if layout.header_row == 3:
        ws["A2"] = "Notes:"
    header_row = layout.header_row
    for idx, header in enumerate(layout.headers, start=1):
        cell = ws.cell(row=header_row, column=idx, value=header)
        cell.font = bold
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # Legacy switch layout (11 cols): Switch Port | Unit | MAC CPE | PPPoE Unit | Notes | AP Make | AP Sticker | AP MAC | Inv Verification | Implication | Action
    widths = {
        "A": 15, "B": 14, "C": 20, "D": 16, "E": 20,
        "F": 20, "G": 20, "H": 20, "I": 28, "J": 26, "K": 22,
    }
    if layout.kind == "physical":
        # Legacy physical layout (10 cols): Unit | MAC CPE | PPPoE Unit | Notes | AP Make | AP Sticker | AP MAC | Inv Verification | Implication | Action
        widths = {
            "A": 14, "B": 20, "C": 16, "D": 20, "E": 20,
            "F": 20, "G": 20, "H": 28, "I": 26, "J": 22,
        }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = f"A{layout.data_start_row}"


def _write_rows(ws, layout: LayoutSpec, rows: list[AuditRow]) -> None:
    xl = _require_openpyxl()
    Table = xl["Table"]
    TableStyleInfo = xl["TableStyleInfo"]
    Font = xl["Font"]
    PatternFill = xl["PatternFill"]
    green_fill = PatternFill("solid", fgColor="C6EFCE")
    yellow_fill = PatternFill("solid", fgColor="FFF2CC")
    red_fill = PatternFill("solid", fgColor="FCE4D6")
    red_font = Font(color="C00000", bold=True)
    # Legacy column layout (switch, 11 cols): Switch Port | Unit | MAC CPE | PPPoE | Notes | AP Make | AP Sticker | AP MAC | Inv Verification | Implication | Action
    # Legacy column layout (physical, 10 cols): Unit | MAC CPE | PPPoE | Notes | AP Make | AP Sticker | AP MAC | Inv Verification | Implication | Action
    row_idx = layout.data_start_row
    for audit_row in rows:
        if layout.kind == "switch":
            values = [
                audit_row.switch_port,
                audit_row.unit_label,
                audit_row.mac_cpe,
                audit_row.pppoe_unit,
                audit_row.notes,
                audit_row.image_ap_make,
                audit_row.image_ap_sticker_apartment,
                audit_row.mac_controller,
                audit_row.inventory_mac_verification,
                audit_row.implication,
                audit_row.action,
            ]
        else:
            values = [
                audit_row.unit_label,
                audit_row.mac_cpe,
                audit_row.pppoe_unit,
                audit_row.notes,
                audit_row.image_ap_make,
                audit_row.image_ap_sticker_apartment,
                audit_row.mac_controller,
                audit_row.inventory_mac_verification,
                audit_row.implication,
                audit_row.action,
            ]
        for col_idx, value in enumerate(values, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)
        row_idx += 1

    n_cols = 11 if layout.kind == "switch" else 10
    last_col = chr(ord("A") + n_cols - 1)
    ref = f"A{layout.header_row}:{last_col}{max(layout.header_row + 1, row_idx - 1)}"
    table = Table(displayName=f"AuditTable{abs(hash(ws.title)) % 100000}", ref=ref)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=False,
        showColumnStripes=False,
    )
    ws.add_table(table)
    for offset, audit_row in enumerate(rows):
        excel_row = layout.data_start_row + offset
        state = _row_state(audit_row)
        fill = green_fill if state == "green" else yellow_fill if state == "yellow" else red_fill
        for col_idx in range(1, n_cols + 1):
            ws.cell(row=excel_row, column=col_idx).fill = fill
        # Highlight the displayed CPE MAC in red when there is a mismatch so it stands out.
        mac_cpe_col_idx = 3 if layout.kind == "switch" else 2
        if state == "yellow" and str(audit_row.mac_cpe or "").strip():
            ws.cell(row=excel_row, column=mac_cpe_col_idx).font = red_font


def generate_nycha_audit_workbook(
    address_text: str,
    out_path: str | Path | None = None,
    template_path: str | Path | None = None,
    ops: Any | None = None,
    _live_context_override: LiveContext | None = None,
) -> dict[str, Any]:
    xl = _require_openpyxl()
    Workbook = xl["Workbook"]
    template = Path(template_path) if template_path else DEFAULT_TEMPLATE_WORKBOOK
    layout = _infer_layout(address_text, template)
    live = _live_context_override or _build_live_context(address_text, ops)
    render_diagnosis = _diagnosis_rendering_enabled_for_address(address_text)
    rows, diagnosis_results_by_unit = _evaluate_rows_with_results(address_text, layout, live, render_diagnosis=render_diagnosis)
    comparison_report = generate_workbook_comparison_report(rows) if CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK else None
    cutover_report = (
        generate_workbook_cutover_report(rows)
        if CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK or render_diagnosis
        else None
    )
    evidence_gap_report = generate_workbook_evidence_gap_report(rows) if CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK else None
    blocker_report = generate_workbook_blocker_report(rows) if CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK else None
    rendered_rows = rows
    rendering_mode = "legacy"
    cutover_blocked_reason = ""
    if render_diagnosis:
        if cutover_report and int(cutover_report.get("rows_blocked_from_cutover") or 0) == 0:
            rendered_rows = [
                _apply_workbook_diagnosis_rendering(row, diagnosis_results_by_unit[row.unit_label])
                if row.unit_label in diagnosis_results_by_unit
                else replace(row)
                for row in rows
            ]
            rendering_mode = "diagnosis"
        else:
            rendering_mode = "legacy_fallback"
            blocked = int((cutover_report or {}).get("rows_blocked_from_cutover") or 0)
            cutover_blocked_reason = (
                f"Diagnosis-driven workbook rendering blocked because {blocked} row(s) are not safe for cutover."
            )

    wb = Workbook()
    ws = wb.active
    _apply_base_formatting(ws, layout, address_text, rendered_rows)
    _write_rows(ws, layout, rendered_rows)

    output_path = Path(out_path) if out_path else PROJECT_ROOT / "output" / "spreadsheet" / f"{_sheet_title_for_address(address_text)}_audit.xlsx"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    serialized_rows = [
        {
            "switch_port": row.switch_port,
            "unit": row.unit_label,
            "mac_cpe": row.mac_cpe,
            "mac_live": row.mac_live,
            "mac_controller": row.mac_controller,
            "pppoe_unit": row.pppoe_unit,
            "notes": row.notes,
            "image_ap_make": row.image_ap_make,
            "inventory_mac_verification": row.inventory_mac_verification,
            "implication": row.implication,
            "action": row.action,
            "state": _row_state(row),
        }
        for row in rendered_rows
    ]
    return {
        "address": address_text,
        "sheet_title": ws.title,
        "layout_kind": layout.kind,
        "row_count": len(rows),
        "template_sheet": layout.donor_sheet_name,
        "live_building_id": live.building_id,
        "live_site_id": live.site_id,
        "live_alert_count": live.active_alert_count,
        "live_online_confirmed_count": sum(1 for row in rendered_rows if row.notes in {"Live online", "Live online via router evidence"}),
        "weighted_ready_percent": _weighted_ready_score(rendered_rows),
        "rows": serialized_rows,
        "comparison_report": comparison_report,
        "cutover_report": cutover_report if CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK or render_diagnosis else None,
        "diagnosis_rendering_enabled_for_address": render_diagnosis,
        "evidence_gap_report": evidence_gap_report,
        "blocker_report": blocker_report,
        "rendering_mode": rendering_mode,
        "cutover_blocked_reason": cutover_blocked_reason,
        "output_path": str(output_path),
    }
