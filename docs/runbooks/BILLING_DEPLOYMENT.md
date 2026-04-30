# Billing Stack Deployment Runbook

How to deploy netbox-billing, netbox-contract, and netbox-stripe-sync to production.

## Prerequisites

- Priority 1 complete: CX-Circuits and Tenants populated for all NYCHA subscribers
- NetBox 4.1.11 running at http://172.27.48.233:8001
- Stripe account with test-mode API keys available
- netbox-billing validated end-to-end in test mode before going live

## Step 1 — Install netbox-contract plugin

On the NetBox server:

```bash
cd /opt/netbox
source venv/bin/activate
pip install netbox-contract   # or install from billing/netbox-contract/
```

Add to `/opt/netbox/netbox/configuration.py`:

```python
PLUGINS = [
    'netbox_contract',
    # ... other plugins
]
PLUGINS_CONFIG = {
    'netbox_contract': {},
}
```

```bash
python manage.py migrate netbox_contract
python manage.py collectstatic --no-input
systemctl restart netbox netbox-rq
```

Verify at: http://172.27.48.233:8001/plugins/contracts/

## Step 2 — Install netbox-billing plugin

```bash
cd /opt/netbox
source venv/bin/activate
pip install -e /opt/lynxnetstack/billing/netbox-billing/
```

Add to `configuration.py`:

```python
PLUGINS = [
    'netbox_contract',
    'netbox_billing',
]
PLUGINS_CONFIG = {
    'netbox_billing': {
        'stripe_api_key': os.environ.get('STRIPE_API_KEY', ''),
        'stripe_webhook_secret': os.environ.get('STRIPE_WEBHOOK_SECRET', ''),
    },
}
```

```bash
python manage.py migrate netbox_billing
python manage.py collectstatic --no-input
systemctl restart netbox netbox-rq
```

Verify at: http://172.27.48.233:8001/plugins/billing/

## Step 3 — Create TariffPlans

In NetBox UI (Plugins → Billing → Tariff Plans) or via API:

```bash
curl -X POST http://172.27.48.233:8001/api/plugins/netbox_billing/tariff-plans/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "NYCHA 100 Mbps",
    "slug": "nycha-100mbps",
    "tariff_type": "internet",
    "monthly_price": "30.00",
    "currency": "usd",
    "download_kbps": 100000,
    "upload_kbps": 100000
  }'
```

Create plans for all NYCHA tiers. Match `download_kbps` to `commit_rate` on CX-Circuits.

## Step 4 — Deploy netbox-stripe-sync

```bash
cd /opt/lynxnetstack/billing/netbox-stripe-sync
cp .env.example .env
# Edit .env with real values:
#   NETBOX_BASE_URL=http://172.27.48.233:8001
#   NETBOX_TOKEN=<token>
#   STRIPE_WEBHOOK_SECRET=whsec_...
#   EVENT_STORE_PATH=/data/events.db

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Install systemd unit
cp /opt/lynxnetstack/deploy/systemd/netbox-stripe-sync.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now netbox-stripe-sync
```

## Step 5 — Register Stripe webhook

In Stripe Dashboard → Developers → Webhooks → Add endpoint:

- URL: `https://<your-domain>/webhooks/stripe`  (or ngrok for testing)
- Events to send:
  - `invoice.paid`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`
  - `invoice.marked_uncollectible`
  - `invoice.voided`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`

Copy the webhook signing secret into `.env` as `STRIPE_WEBHOOK_SECRET`.

## Step 6 — Import Splynx Stripe customer IDs

```bash
# Export from Splynx: Finance → Customers → Export CSV with stripe_customer_id column
# Then:
cd /opt/lynxnetstack
python billing/scripts/import_splynx_stripe_customers.py \
  --csv /tmp/splynx_stripe_export.csv \
  --dry-run   # review output first

python billing/scripts/import_splynx_stripe_customers.py \
  --csv /tmp/splynx_stripe_export.csv   # real run
```

## Step 7 — Test end-to-end in Stripe test mode

1. Create a test PaymentIntent for a BillingAccount in test mode
2. Trigger a `invoice.paid` event via Stripe CLI: `stripe trigger invoice.paid`
3. Verify netbox-stripe-sync logs show the event processed
4. Verify the Invoice in NetBox shows `status=paid`

Only proceed to live Stripe keys after test-mode works end-to-end.

## Step 8 — Switch to Stripe live mode

1. Replace `STRIPE_API_KEY` in NetBox configuration with live key (`sk_live_...`)
2. Replace `STRIPE_WEBHOOK_SECRET` with live webhook secret
3. Register a second Stripe webhook endpoint pointing to production URL
4. Restart NetBox and netbox-stripe-sync

## Do NOT Cancel Splynx Until

- [ ] All subscribers have BillingAccounts in NetBox with valid Stripe customer IDs
- [ ] At least one full billing cycle completed successfully in production Stripe
- [ ] Invoice webhook events are confirmed reaching NetBox and updating status
- [ ] Payment failure handling is verified (subscriber status suspension flow)
- [ ] Operator staff trained on LynxMSP billing UI
