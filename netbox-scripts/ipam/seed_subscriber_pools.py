"""
netbox-scripts/ipam/seed_subscriber_pools.py

Creates the NYCHA subscriber IP pool prefixes in NetBox IPAM.

Pools:
  10.0.8.0/24  through  10.0.14.0/24  (7 x /24)

Each prefix is:
  - status: active
  - role: Subscriber
  - is_pool: true
  - site: 000007 (NYCHA)
  - vlan: VLAN 20 (subscriber/customer)

Run once before kea-sync starts writing IPs.

Usage:
  export NETBOX_URL=http://172.27.48.233:8001
  export NETBOX_TOKEN=<token>
  python seed_subscriber_pools.py
"""

import os
import sys
import requests

# WHY: Default matches ResiBridge production NetBox. Override with NETBOX_URL env var.
NETBOX_URL = os.environ.get("NETBOX_URL", "http://172.27.48.233:8001").rstrip("/")
NETBOX_TOKEN = os.environ.get("NETBOX_TOKEN", "")
HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Site slug for which to create subscriber IP pools.
# Override with SITE_SLUG env var for non-NYCHA deployments.
SITE_SLUG = os.environ.get("SITE_SLUG", "000007")

# Prefixes to create
SUBSCRIBER_POOLS = [
    "10.0.8.0/24",
    "10.0.9.0/24",
    "10.0.10.0/24",
    "10.0.11.0/24",
    "10.0.12.0/24",
    "10.0.13.0/24",
    "10.0.14.0/24",
]


def nb_get(path, params=None):
    url = f"{NETBOX_URL}/api/{path.lstrip('/')}"
    resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def nb_post(path, body):
    url = f"{NETBOX_URL}/api/{path.lstrip('/')}"
    resp = requests.post(url, headers=HEADERS, json=body, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_or_create_role(name, slug):
    """Get or create an IP prefix role."""
    results = nb_get("ipam/roles/", {"slug": slug}).get("results", [])
    if results:
        return results[0]["id"]
    created = nb_post("ipam/roles/", {"name": name, "slug": slug})
    print(f"  Created role: {name}")
    return created["id"]


def get_site_id(slug):
    results = nb_get("dcim/sites/", {"slug": slug}).get("results", [])
    if not results:
        print(f"ERROR: Site '{slug}' not found in NetBox.", file=sys.stderr)
        sys.exit(1)
    return results[0]["id"]


def prefix_exists(prefix):
    results = nb_get("ipam/prefixes/", {"prefix": prefix}).get("results", [])
    return bool(results)


def main():
    if not NETBOX_TOKEN:
        print("ERROR: NETBOX_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to NetBox at {NETBOX_URL}")
    site_id = get_site_id(SITE_SLUG)
    print(f"  Site 000007 id={site_id}")

    role_id = get_or_create_role("Subscriber", "subscriber")
    print(f"  Role 'Subscriber' id={role_id}")

    for prefix in SUBSCRIBER_POOLS:
        if prefix_exists(prefix):
            print(f"  SKIP  {prefix} — already exists")
            continue
        nb_post("ipam/prefixes/", {
            "prefix": prefix,
            "status": "active",
            "is_pool": True,
            "site": site_id,
            "role": role_id,
            "description": f"NYCHA 000007 subscriber pool — {prefix}",
        })
        print(f"  CREATE {prefix}")

    print("Done.")


if __name__ == "__main__":
    main()
