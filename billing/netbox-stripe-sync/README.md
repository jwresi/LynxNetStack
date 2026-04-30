# NetBox Stripe Sync

Billing service and UI that sync Stripe events into `netbox-contract` and provides NetBox-backed operations.

## What It Does

- Receives Stripe webhook events.
- Verifies signatures with `STRIPE_WEBHOOK_SECRET` (if configured).
- Maps Stripe objects to NetBox plugin objects.
- Writes status/comments back to:
  - `Invoice` (`invoice.*` events)
  - `Contract` (`customer.subscription.updated|deleted`)
- Stores processed event IDs in SQLite for idempotency.
- Serves a modern web UI for:
  - customer (tenant) browsing/editing,
  - invoice visibility,
  - hardware checkout/move between customers and sites.

## UI

- URL: `/`
- Backed by service endpoints under `/api/app/*`
- Main views:
  - Dashboard
  - Customers
  - Invoices
  - Hardware Checkout

Hardware checkout endpoint:
- `POST /api/app/hardware/checkout`
  - updates device `tenant`/`site`
  - appends an operation note to device comments

## Current Mapping Logic

### Invoice events

Handled:
- `invoice.paid` -> invoice `status=posted`
- `invoice.payment_succeeded` -> invoice `status=posted`
- `invoice.payment_failed` -> invoice `status=draft`
- `invoice.marked_uncollectible` -> invoice `status=draft`
- `invoice.voided` -> invoice `status=canceled`

Invoice lookup order:
1. `invoice.metadata.netbox_invoice_id`
2. `invoice.metadata.netbox_invoice_number`
3. `invoice.metadata.invoice_number`
4. `invoice.number`

### Subscription events

Handled:
- `customer.subscription.updated`
- `customer.subscription.deleted`

Contract lookup order:
1. `subscription.metadata.netbox_contract_id`
2. `contract.external_reference == subscription.id`

Contract status mapping:
- `canceled|unpaid|incomplete_expired` -> `canceled`
- all others -> `active`

## NetBox Plugin Requirement

The plugin API serializer must expose invoice `status` to allow webhook updates.
This repository includes the required patch in:

- `netbox_contract/api/serializers.py`

## Environment Variables

See `.env.example`.

Required:
- `NETBOX_BASE_URL`
- `NETBOX_TOKEN`

Optional:
- `STRIPE_WEBHOOK_SECRET` (strongly recommended)
- `EVENT_STORE_PATH` (default: `/data/events.db`)
- `WEBHOOK_LISTEN_HOST` (default: `0.0.0.0`)
- `WEBHOOK_LISTEN_PORT` (default: `8080`)

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export NETBOX_BASE_URL="http://netbox.local"
export NETBOX_TOKEN="..."
export STRIPE_WEBHOOK_SECRET="whsec_..."
export EVENT_STORE_PATH="./events.db"

uvicorn app.main:app --reload --port 8080
```

Health check:

```bash
curl -s http://127.0.0.1:8080/health
```

Open UI:

```bash
open http://127.0.0.1:8080
```

## Stripe Webhook Setup

Example:

```bash
stripe listen --forward-to http://127.0.0.1:8080/webhooks/stripe
```

For reliable mapping, set metadata in Stripe invoice/subscription objects:

- `netbox_invoice_id` or `netbox_invoice_number`
- `netbox_contract_id` (for subscription events)

## Notes

- The service writes event traces into NetBox `comments` fields.
- Unknown/unhandled events are acknowledged and ignored.
- Duplicate events are ignored using local event storage.
- The NetBox API token must have rights to read/write:
  - plugin contracts/invoices,
  - tenants,
  - sites/devices.
