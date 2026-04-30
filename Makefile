.PHONY: up down logs build ps jake2-setup provisioner-up kea-setup netbox-scripts-setup help

# ── Docker Compose (full stack) ───────────────────────────────────────────────

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

ps:
	docker compose ps

# ── Per-component targets ─────────────────────────────────────────────────────

jake2-setup:
	cd jake2 && python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
	@echo "Jake2 venv ready. Copy jake2/config/.env.example -> jake2/config/.env and fill in values."

jake2-serve:
	cd jake2 && ./jake --serve

provisioner-up:
	cd provisioner && make up

tikfig-serve:
	cd tikfig && python app.py

kea-setup:
	cd kea-sync && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	@echo "kea-sync venv ready."

kea-run:
	cd kea-sync && .venv/bin/python lease_poller.py

# ── NetBox migration scripts ──────────────────────────────────────────────────

seed-ipam:
	@echo "Seeding NYCHA subscriber IP pools in NetBox..."
	cd netbox-scripts/ipam && python seed_subscriber_pools.py

populate-cx-circuits:
	@test -n "$(CSV)" || (echo "Usage: make populate-cx-circuits CSV=/path/to/subscribers.csv" && exit 1)
	cd netbox-scripts/cx_circuits && python populate_cx_circuits.py --source-csv $(CSV)

populate-cx-circuits-dry:
	@test -n "$(CSV)" || (echo "Usage: make populate-cx-circuits-dry CSV=/path/to/subscribers.csv" && exit 1)
	cd netbox-scripts/cx_circuits && python populate_cx_circuits.py --source-csv $(CSV) --dry-run

export-subscribers:
	cd jake2 && .venv/bin/python scripts/export_nycha_subscribers.py --output /tmp/nycha_subscribers.csv
	@echo "Exported to /tmp/nycha_subscribers.csv"

# ── Billing ───────────────────────────────────────────────────────────────────

stripe-sync-run:
	cd billing/netbox-stripe-sync && .venv/bin/uvicorn app.main:app --reload --port 8083

import-stripe-customers:
	@test -n "$(CSV)" || (echo "Usage: make import-stripe-customers CSV=/path/to/splynx_stripe_export.csv" && exit 1)
	python billing/scripts/import_splynx_stripe_customers.py --csv $(CSV)

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "LynxNetStack Makefile targets:"
	@echo ""
	@echo "  Full stack:"
	@echo "    make up                  Start all services (Docker)"
	@echo "    make down                Stop all services"
	@echo "    make logs                Follow all logs"
	@echo "    make build               Rebuild Docker images"
	@echo ""
	@echo "  Components:"
	@echo "    make jake2-setup         Setup Jake2 Python venv"
	@echo "    make jake2-serve         Start Jake2 WebUI on :8080"
	@echo "    make provisioner-up      Start Provisioner (frontend :3001, backend :5001)"
	@echo "    make tikfig-serve        Start Tikfig on :8082"
	@echo "    make kea-setup           Setup kea-sync venv"
	@echo "    make kea-run             Run kea-sync lease poller"
	@echo "    make stripe-sync-run     Start netbox-stripe-sync on :8083"
	@echo ""
	@echo "  NetBox migration:"
	@echo "    make seed-ipam           Create subscriber IP pools in NetBox"
	@echo "    make export-subscribers  Export NYCHA subscribers from Jake2 to CSV"
	@echo "    make populate-cx-circuits CSV=<path>   Populate CX-Circuits in NetBox"
	@echo "    make populate-cx-circuits-dry CSV=<path>  Dry-run CX-Circuit population"
	@echo ""
	@echo "  Billing:"
	@echo "    make import-stripe-customers CSV=<path>  Import Splynx Stripe IDs"
	@echo ""
