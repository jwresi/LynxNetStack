"""
billing/scripts/import_splynx_stripe_customers.py

Priority 3: Import existing Splynx Stripe customer IDs into netbox-billing
BillingAccount records, linking them to the correct NetBox Tenants.

Prerequisites:
  - netbox-billing plugin installed and migrated in production NetBox
  - CX-Circuit subscriber model fully populated (Priority 1 complete)
  - Splynx Stripe customer export CSV available

CSV format (export from Splynx admin -> Finance -> Customers):
  service_login, stripe_customer_id, name, email, plan_name

Usage:
  export NETBOX_URL=http://172.27.48.233:8001
  export NETBOX_TOKEN=<token>
  python import_splynx_stripe_customers.py --csv /path/to/splynx_stripe_export.csv
"""

import argparse
import csv
import os
import sys
import requests

NETBOX_URL = os.environ.get("NETBOX_URL", "http://172.27.48.233:8001").rstrip("/")
NETBOX_TOKEN = os.environ.get("NETBOX_TOKEN", "")
HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


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


def find_tenant_by_service_login(service_login):
    """
    Find a NetBox Tenant matching the Splynx service_login.
    service_login is typically the unit label (e.g. "1B") or a CX-Circuit CID.
    We check both tenant name and CX-Circuit CID.
    """
    # Try by tenant name first
    results = nb_get("tenancy/tenants/", {"name": service_login})
    if results:
        return results[0]
    # Try by circuit CID
    circuits = nb_get("circuits/circuits/", {"cid": service_login})
    if circuits:
        tenant = circuits[0].get("tenant")
        if tenant:
            tenant_results = nb_get(f"tenancy/tenants/{tenant['id']}/")
            if tenant_results:
                return tenant_results[0] if isinstance(tenant_results, list) else tenant_results
    return None


def get_or_create_billing_account(tenant_id, stripe_customer_id, email, dry_run):
    """Create or update a BillingAccount for this tenant."""
    # netbox-billing exposes BillingAccount under plugins API
    results = nb_get("plugins/netbox_billing/billing-accounts/", {"tenant_id": tenant_id})
    if results:
        account = results[0]
        if account.get("stripe_customer_id") != stripe_customer_id:
            if not dry_run:
                nb_patch(f"plugins/netbox_billing/billing-accounts/{account['id']}/", {
                    "stripe_customer_id": stripe_customer_id,
                    "billing_email": email or "",
                })
            print(f"  UPDATE BillingAccount tenant={tenant_id} stripe={stripe_customer_id}")
        return account["id"]

    if dry_run:
        print(f"  [DRY] Would create BillingAccount tenant={tenant_id} stripe={stripe_customer_id}")
        return None

    created = nb_post("plugins/netbox_billing/billing-accounts/", {
        "tenant": tenant_id,
        "status": "active",
        "stripe_customer_id": stripe_customer_id,
        "billing_email": email or "",
        "autopay_enabled": True,
    })
    print(f"  CREATE BillingAccount tenant={tenant_id} stripe={stripe_customer_id}")
    return created["id"]


def main():
    parser = argparse.ArgumentParser(description="Import Splynx Stripe customer IDs into netbox-billing")
    parser.add_argument("--csv", required=True, help="Path to Splynx Stripe export CSV")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not NETBOX_TOKEN:
        print("ERROR: NETBOX_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    matched = 0
    unmatched = []

    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Processing {len(rows)} Splynx Stripe records...")

    for row in rows:
        service_login = row.get("service_login", "").strip()
        stripe_id = row.get("stripe_customer_id", "").strip()
        email = row.get("email", "").strip()

        if not stripe_id:
            continue

        tenant = find_tenant_by_service_login(service_login)
        if not tenant:
            unmatched.append(service_login)
            continue

        get_or_create_billing_account(tenant["id"], stripe_id, email, args.dry_run)
        matched += 1

    print(f"\nMatched: {matched}  Unmatched: {len(unmatched)}")
    if unmatched:
        print("Unmatched service logins (no NetBox tenant found):")
        for sl in unmatched[:20]:
            print(f"  {sl}")
        if len(unmatched) > 20:
            print(f"  ... and {len(unmatched) - 20} more")


if __name__ == "__main__":
    main()
