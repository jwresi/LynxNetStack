"""
jake2/scripts/export_nycha_subscribers.py

Exports NYCHA subscriber data from Jake2's scan DB + Splynx Prometheus
into a CSV suitable for netbox-scripts/cx_circuits/populate_cx_circuits.py.

Output columns:
  building_id, building_name, unit, switch_name, interface,
  name, email, phone, commit_rate_kbps

Usage:
  cd jake2
  python scripts/export_nycha_subscribers.py > /tmp/subscribers.csv
  python scripts/export_nycha_subscribers.py --site 000007 --output /tmp/subs.csv
"""

import argparse
import csv
import os
import sys

# WHY: Jake2 is run from its own directory as an installed package.
# We rely on pyproject.toml entry points and do NOT mutate sys.path here.

SITE_DEFAULT = "000007"


def load_jake2_ops():
    """Load Jake2 ops layer (requires jake2 installed/venv active)."""
    try:
        from pathlib import Path
        env_path = Path("config/.env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
        from mcp.jake_ops_mcp import JakeOps
        return JakeOps()
    except ImportError as exc:
        print(f"ERROR: Cannot import JakeOps — are you in the jake2 venv? {exc}", file=sys.stderr)
        sys.exit(1)


def fetch_nycha_inventory(ops, site_id):
    """
    Pull nycha_live_inventory from Jake2.
    Returns list of dicts with keys:
      switch_identity, interface, building_id, unit, mac
    """
    try:
        return ops.nycha_live_inventory(site_id=site_id) or []
    except Exception as exc:  # pylint: disable=broad-except
        print(f"WARN: nycha_live_inventory failed: {exc}", file=sys.stderr)
        return []


def fetch_splynx_subscribers(ops, site_id):
    """
    Pull Splynx subscriber data from Prometheus via Jake2.
    Returns list of dicts with keys: service_login, name, email, phone, ipv4, session_mac
    """
    try:
        return ops.splynx_subscribers(site_id=site_id) or []
    except Exception as exc:  # pylint: disable=broad-except
        print(f"WARN: splynx_subscribers failed: {exc}", file=sys.stderr)
        return []


def infer_building_name(building_id):
    """
    Return a human-readable building name from building_id if known.
    Extend this dict as buildings are mapped.
    """
    known = {
        "000007.001": "104 Tapscott",
        "000007.002": "168 Bradford",
        "000007.003": "174 Bradford",
        # Add more as discovered
    }
    return known.get(building_id, building_id)


def main():
    parser = argparse.ArgumentParser(description="Export NYCHA subscribers from Jake2")
    parser.add_argument("--site", default=SITE_DEFAULT, help="Site ID (default: 000007)")
    parser.add_argument("--output", default="-", help="Output CSV path (default: stdout)")
    args = parser.parse_args()

    ops = load_jake2_ops()

    inventory = fetch_nycha_inventory(ops, args.site)
    splynx_subs = fetch_splynx_subscribers(ops, args.site)

    # Index Splynx data by MAC for join
    splynx_by_mac = {}
    for sub in splynx_subs:
        mac = (sub.get("session_mac") or "").lower().replace("-", ":").strip()
        if mac:
            splynx_by_mac[mac] = sub

    fieldnames = [
        "building_id", "building_name", "unit",
        "switch_name", "interface",
        "name", "email", "phone", "commit_rate_kbps",
    ]

    out = open(args.output, "w", newline="", encoding="utf-8") if args.output != "-" else sys.stdout
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()

    seen_units = set()
    for entry in inventory:
        building_id = entry.get("building_id", "")
        unit = entry.get("unit", "")
        switch_name = entry.get("switch_identity", "")
        interface = entry.get("interface", "")
        mac = (entry.get("mac") or "").lower().replace("-", ":").strip()

        if not building_id or not unit:
            continue

        key = (building_id, unit)
        if key in seen_units:
            continue
        seen_units.add(key)

        splynx = splynx_by_mac.get(mac, {})

        writer.writerow({
            "building_id":      building_id,
            "building_name":    infer_building_name(building_id),
            "unit":             unit,
            "switch_name":      switch_name,
            "interface":        interface,
            "name":             splynx.get("name", ""),
            "email":            splynx.get("email", ""),
            "phone":            splynx.get("phone", ""),
            "commit_rate_kbps": 100_000,  # Default 100 Mbps; override per plan if needed
        })

    if args.output != "-":
        out.close()
        print(f"Wrote {len(seen_units)} records to {args.output}", file=sys.stderr)
    else:
        print(f"# {len(seen_units)} records exported", file=sys.stderr)


if __name__ == "__main__":
    main()
