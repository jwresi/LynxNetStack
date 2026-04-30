# NetBox Billing Plugin (MVP)

`netbox-billing` is a unified billing plugin for NetBox combining:
- Tariff/package catalog
- Property + unit service inventory
- Customer billing accounts (tenant-linked)
- Subscriptions linked to CPE devices
- Invoices and line items
- Scheduled Stripe payments
- Stripe webhook event capture

## Status
MVP scaffold for rapid iteration. Includes NetBox UI views, CX retro UI, and REST API viewsets.

## Compatibility
- NetBox Community: `4.1.11` only
- Plugin config: `min_version = 4.1.11`, `max_version = 4.1.11`

## Install (development)
1. Install plugin package in NetBox environment:
```bash
python -m pip install -e /path/to/netbox-billing
```
2. Add plugin in `configuration.py`:
```python
PLUGINS = [
    'netbox_billing',
]

PLUGINS_CONFIG = {
    'netbox_billing': {
        'stripe_api_key': 'sk_live_or_test_key',
        'cx_groups': ['cx', 'customer_experience', 'csr'],
    }
}
```
3. Run migrations:
```bash
python manage.py migrate
```
4. Grant CX group permissions:
```bash
python manage.py sync_cx_permissions
```

## Payment Scheduling
- CX UI supports immediate Stripe charges and scheduled charges from customer billing tab.
- Scheduled payments can be processed with:
```bash
python manage.py process_scheduled_payments
```
- NetBox Job available: `Process Scheduled Payments` (can be scheduled in NetBox jobs UI).
