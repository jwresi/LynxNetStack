"""
netbox-scripts/cx_circuits/populate_cx_circuits.py

Priority 1: Scale the CX-Circuit subscriber model to all NYCHA subscribers.

For each subscriber sourced from Jake2's nycha_live_inventory:
  1. Create Tenant Group for the building (if not exists)
  2. Create Tenant for the unit (if not exists)
  3. Create CX-Circuit (provider=Lynxnet, type=CX-Circuit, tenant=Tenant)
  4. Create Contact (name, email, phone) and link to Circuit (role=Customer)
  5. Link circuit termination_z -> switch interface via cable

Data model constraints:
  - All circuits: provider slug = 'lynxnet' (id=9 in prod)
  - All circuits: type slug = 'cx-circuit' (id=3 in prod)
  - Switch interface naming: ETH{N} (ether3 -> ETH3)
  - Plan speed encoded in commit_rate (kbps): 100 Mbps = 100000, 1 Gbps = 1000000

Source data (from Jake2 scan DB / Splynx Prometheus):
  - switch_identity  e.g. "000007.001.SW01"
  - interface        e.g. "ether3"
  - building_id      e.g. "000007.001"
  - unit             e.g. "1B"
  - mac              subscriber MAC
  - name             subscriber name (from Splynx)
  - email            subscriber email
  - phone            subscriber phone
  - commit_rate_kbps plan speed in kbps

Usage:
  export NETBOX_URL=http://172.27.48.233:8001
  export NETBOX_TOKEN=<token>
  python populate_cx_circuits.py [--dry-run] [--source-csv path/to/subscribers.csv]
"""

import argparse
import csv
import os
import sys
import time
import requests

# WHY: Default matches ResiBridge production NetBox. Override with NETBOX_URL env var.
NETBOX_URL = os.environ.get("NETBOX_URL", "http://172.27.48.233:8001").rstrip("/")
NETBOX_TOKEN = os.environ.get("NETBOX_TOKEN", "")
HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Production IDs — verify before running
PROVIDER_SLUG = "lynxnet"
CIRCUIT_TYPE_SLUG = "cx-circuit"
CONTACT_ROLE_SLUG = "customer"

DEFAULT_COMMIT_RATE_KBPS = 100_000   # 100 Mbps


def nb_get(path, params=None):
    url = f"{NETBOX_URL}/api/{path.lstrip('/')}"
    resp = requests.get(url, headers=HEADERS, params=params or {}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("results", [])


def nb_post(path, body):
    url = f"{NETBOX_URL}/api/{path.lstrip('/')}"
    resp = requests.post(url, headers=HEADERS, json=body, timeout=10)
    resp.raise_for_status()
    return resp.json()


def nb_patch(path, body):
    url = f"{NETBOX_URL}/api/{path.lstrip('/')}"
    resp = requests.patch(url, headers=HEADERS, json=body, timeout=10)
    resp.raise_for_status()
    return resp.json()

# ── Cache helpers ─────────────────────────────────────────────────────────────

_cache = {}


def _cached(key, fn):
    if key not in _cache:
        _cache[key] = fn()
    return _cache[key]


def get_provider_id():
    def _fetch():
        results = nb_get("circuits/providers/", {"slug": PROVIDER_SLUG})
        if not results:
            raise RuntimeError(f"Provider '{PROVIDER_SLUG}' not found. Create it first.")
        return results[0]["id"]
    return _cached("provider_id", _fetch)


def get_circuit_type_id():
    def _fetch():
        results = nb_get("circuits/circuit-types/", {"slug": CIRCUIT_TYPE_SLUG})
        if not results:
            raise RuntimeError(f"Circuit type '{CIRCUIT_TYPE_SLUG}' not found. Create it first.")
        return results[0]["id"]
    return _cached("circuit_type_id", _fetch)


def get_contact_role_id():
    def _fetch():
        results = nb_get("tenancy/contact-roles/", {"slug": CONTACT_ROLE_SLUG})
        if results:
            return results[0]["id"]
        # Create if missing
        created = nb_post("tenancy/contact-roles/", {"name": "Customer", "slug": "customer"})
        print(f"  Created contact role: Customer")
        return created["id"]
    return _cached("contact_role_id", _fetch)


# ── Core object builders ──────────────────────────────────────────────────────


def get_or_create_tenant_group(building_id, building_name, dry_run):
    results = nb_get("tenancy/tenant-groups/", {"slug": building_id.lower().replace(".", "-")})
    if results:
        return results[0]["id"]
    if dry_run:
        print(f"    [DRY] Would create TenantGroup: {building_id} ({building_name})")
        return None
    slug = building_id.lower().replace(".", "-")
    created = nb_post("tenancy/tenant-groups/", {
        "name": building_id,
        "slug": slug,
        "description": building_name or building_id,
    })
    print(f"    CREATE TenantGroup: {building_id}")
    return created["id"]


def get_or_create_tenant(unit, building_group_id, dry_run):
    slug = unit.lower().replace(" ", "-").replace("/", "-")
    results = nb_get("tenancy/tenants/", {"slug": slug, "group_id": building_group_id})
    if results:
        return results[0]["id"]
    if dry_run:
        print(f"    [DRY] Would create Tenant: {unit}")
        return None
    created = nb_post("tenancy/tenants/", {
        "name": unit,
        "slug": slug,
        "group": building_group_id,
    })
    print(f"    CREATE Tenant: {unit}")
    return created["id"]


def get_or_create_contact(name, email, phone, dry_run):
    if email:
        results = nb_get("tenancy/contacts/", {"email": email})
        if results:
            return results[0]["id"]
    if dry_run:
        print(f"    [DRY] Would create Contact: {name} <{email}>")
        return None
    body = {"name": name or "Unknown"}
    if email:
        body["email"] = email
    if phone:
        body["phone"] = phone
    created = nb_post("tenancy/contacts/", body)
    print(f"    CREATE Contact: {name}")
    return created["id"]


def circuit_exists(cid):
    results = nb_get("circuits/circuits/", {"cid": cid})
    return results[0]["id"] if results else None


def create_circuit(cid, tenant_id, commit_rate_kbps, site_id, dry_run):
    existing_id = circuit_exists(cid)
    if existing_id:
        return existing_id
    if dry_run:
        print(f"    [DRY] Would create CX-Circuit: {cid}")
        return None
    created = nb_post("circuits/circuits/", {
        "cid": cid,
        "provider": get_provider_id(),
        "type": get_circuit_type_id(),
        "tenant": tenant_id,
        "status": "active",
        "commit_rate": commit_rate_kbps,
        "site": site_id,
    })
    print(f"    CREATE Circuit: {cid}")
    return created["id"]


def link_contact_to_circuit(contact_id, circuit_id, dry_run):
    # Check if assignment already exists
    results = nb_get("tenancy/contact-assignments/", {
        "content_type": "circuits.circuit",
        "object_id": circuit_id,
        "contact_id": contact_id,
    })
    if results:
        return
    if dry_run:
        print(f"    [DRY] Would assign contact {contact_id} to circuit {circuit_id}")
        return
    nb_post("tenancy/contact-assignments/", {
        "content_type": "circuits.circuit",
        "object_id": circuit_id,
        "contact": contact_id,
        "role": get_contact_role_id(),
    })
    print(f"    ASSIGN Contact -> Circuit {circuit_id}")


def link_circuit_to_port(circuit_id, switch_name, ether_iface, dry_run):
    """
    Create circuit termination Z and cable it to the switch interface.

    switch_name:  e.g. "000007.001.SW01"
    ether_iface:  e.g. "ether3"  (RouterOS name — converted to ETH3 for NetBox)
    """
    nb_iface_name = routeros_to_netbox_iface(ether_iface)

    # Find the switch device
    devices = nb_get("dcim/devices/", {"name": switch_name})
    if not devices:
        print(f"    WARN: Device '{switch_name}' not found in NetBox — skipping port link")
        return
    device_id = devices[0]["id"]

    # Find the interface
    ifaces = nb_get("dcim/interfaces/", {"device_id": device_id, "name": nb_iface_name})
    if not ifaces:
        print(f"    WARN: Interface '{nb_iface_name}' not found on {switch_name} — skipping")
        return
    iface_id = ifaces[0]["id"]

    # Check if circuit already has a termination Z
    terms = nb_get("circuits/circuit-terminations/", {"circuit_id": circuit_id, "term_side": "Z"})
    if terms:
        return  # Already linked

    if dry_run:
        print(f"    [DRY] Would cable {switch_name}.{nb_iface_name} -> circuit {circuit_id}")
        return

    # Create circuit termination Z
    term = nb_post("circuits/circuit-terminations/", {
        "circuit": circuit_id,
        "term_side": "Z",
    })
    term_id = term["id"]

    # Create cable: interface <-> circuit termination
    nb_post("dcim/cables/", {
        "a_terminations": [{"object_type": "dcim.interface", "object_id": iface_id}],
        "b_terminations": [{"object_type": "circuits.circuittermination", "object_id": term_id}],
        "status": "connected",
    })
    print(f"    CABLE {switch_name}.{nb_iface_name} <-> circuit {circuit_id}")


def routeros_to_netbox_iface(ros_name):
    """Convert RouterOS ether3 -> ETH3 for NetBox."""
    if ros_name.lower().startswith("ether"):
        return f"ETH{ros_name[5:]}"
    return ros_name.upper()


def get_site_id_for_building(building_id):
    """Look up the NetBox site for a building. Uses building_id as site slug."""
    slug = building_id.split(".")[0].lower()  # "000007.001" -> "000007"
    results = nb_get("dcim/sites/", {"slug": slug})
    return results[0]["id"] if results else None


# ── CSV loader ────────────────────────────────────────────────────────────────


def load_from_csv(path):
    """
    Load subscriber records from a CSV file.

    Expected columns (all optional except building_id + unit):
      building_id, building_name, unit, switch_name, interface,
      name, email, phone, commit_rate_kbps
    """
    records = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append({
                "building_id":      row.get("building_id", "").strip(),
                "building_name":    row.get("building_name", "").strip(),
                "unit":             row.get("unit", "").strip(),
                "switch_name":      row.get("switch_name", "").strip(),
                "interface":        row.get("interface", "").strip(),
                "name":             row.get("name", "").strip(),
                "email":            row.get("email", "").strip(),
                "phone":            row.get("phone", "").strip(),
                "commit_rate_kbps": int(row.get("commit_rate_kbps") or DEFAULT_COMMIT_RATE_KBPS),
            })
    return records


# ── Main ──────────────────────────────────────────────────────────────────────


def process_subscriber(sub, dry_run):
    building_id   = sub["building_id"]
    building_name = sub["building_name"] or building_id
    unit          = sub["unit"]
    switch_name   = sub["switch_name"]
    ether_iface   = sub["interface"]
    sub_name      = sub["name"] or f"{building_id}/{unit}"
    email         = sub["email"]
    phone         = sub["phone"]
    commit_rate   = sub["commit_rate_kbps"]

    if not building_id or not unit:
        print(f"  SKIP: missing building_id or unit in record {sub}")
        return

    cid = f"{building_id}.{unit}"   # e.g. "000007.001.1B"

    # 1. Tenant Group (building)
    group_id = get_or_create_tenant_group(building_id, building_name, dry_run)

    # 2. Tenant (unit)
    tenant_id = get_or_create_tenant(unit, group_id, dry_run)

    # 3. Site
    site_id = get_site_id_for_building(building_id)

    # 4. CX-Circuit
    circuit_id = create_circuit(cid, tenant_id, commit_rate, site_id, dry_run)

    # 5. Contact
    if sub_name:
        contact_id = get_or_create_contact(sub_name, email, phone, dry_run)
        if contact_id and circuit_id:
            link_contact_to_circuit(contact_id, circuit_id, dry_run)

    # 6. Port link (cable)
    if switch_name and ether_iface and circuit_id:
        link_circuit_to_port(circuit_id, switch_name, ether_iface, dry_run)

    time.sleep(0.1)  # Be gentle with the NetBox API


def main():
    parser = argparse.ArgumentParser(description="Populate NetBox CX-Circuit subscriber records")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without writing to NetBox")
    parser.add_argument("--source-csv", default=None, help="Path to subscriber CSV")
    args = parser.parse_args()

    if not NETBOX_TOKEN:
        print("ERROR: NETBOX_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    if not args.source_csv:
        print("ERROR: --source-csv is required", file=sys.stderr)
        print("  Generate the CSV from Jake2:")
        print("    cd jake2 && python scripts/export_nycha_subscribers.py > /tmp/subscribers.csv")
        sys.exit(1)

    print(f"NetBox: {NETBOX_URL}")
    if args.dry_run:
        print("DRY RUN — no changes will be written")

    # Pre-fetch shared IDs once
    print(f"  Provider '{PROVIDER_SLUG}': id={get_provider_id()}")
    print(f"  Circuit type '{CIRCUIT_TYPE_SLUG}': id={get_circuit_type_id()}")

    records = load_from_csv(args.source_csv)
    print(f"  Loaded {len(records)} subscriber records from {args.source_csv}")

    errors = 0
    for i, sub in enumerate(records, 1):
        try:
            process_subscriber(sub, args.dry_run)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  ERROR record {i} ({sub.get('building_id')}/{sub.get('unit')}): {exc}")
            errors += 1

    print(f"\nDone. {len(records)} records, {errors} errors.")


if __name__ == "__main__":
    main()
