# CLAUDE.md — LynxNetStack

This file provides guidance to Claude Code when working in this repository.

## What This Is

LynxNetStack is the unified ISP management platform for ResiBridge, a WISP/MDU operator serving NYCHA public housing in Brooklyn, NY. It manages subscriber identity, DHCP lease tracking, billing, asset inventory, and network operations on a MikroTik-heavy access network.

## Production Services (Always Live)

| Service | Address | Notes |
|---------|---------|-------|
| NetBox | `http://172.27.48.233:8001` | Source of truth. Token in `jake2/config/.env` |
| BigMac (RouterOS API proxy) | `http://172.27.226.246:8081` | All live switch reads go through here |
| Prometheus | `http://172.27.72.179:9090` | Metrics for switches, CPE, OLT |
| Kea DHCP4 (target) | `172.27.28.50` | Ubuntu 22.04 VM, not yet deployed |
| Splynx | Live | Active billing — do NOT cancel |

## Key Commands Per Component

### Jake2
```bash
cd jake2
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
cp config/.env.example config/.env
.venv/bin/python -m pytest -q        # tests
.venv/bin/python -m core.jake_query  # CLI
./jake --serve                        # WebUI + API on :8080
```

### Provisioner
```bash
cd provisioner
make up    # frontend :3000, backend :5001
make logs
make down
```

### Tikfig
```bash
cd tikfig
cp config.example.yml config.yml
pip install -r requirements.txt
python app.py   # :8080
```

### ssh_mcp
```bash
cd ssh_mcp
cp config/ssh_mcp.example.json config/ssh_mcp.json
pip install -e .
python -m ssh_mcp.server
```

### Kea Sync
```bash
cd kea-sync
pip install -r requirements.txt
python lease_poller.py
```

### Billing (netbox-stripe-sync)
```bash
cd billing/netbox-stripe-sync
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Architecture: Never Break These

1. Subscriber identity = standard NetBox (Tenant Group → Tenant → CX-Circuit → switch interface). Not billing plugin fields.
2. Jake2: understanding layer (`core/intent_parser.py`) and execution layer (`core/query_core.py`) are STRICTLY separated. Never merge.
3. NetBox interface naming = `ETH{N}` (not RouterOS `ether{N}`). Mapping: ether3 → ETH3.
4. Circuit-id format from RouterOS 7.21+: `<interface>:<vid>` e.g. `ether3:20`.
5. HW offload is OFF site-wide on all NYCHA switches. Do not re-enable.

## Current Migration Priority

1. Scale CX-Circuit model to all NYCHA subscribers (script: `netbox-scripts/cx_circuits/populate_cx_circuits.py`)
2. Deploy and configure Kea DHCP4 on 172.27.28.50
3. Run kea-sync lease poller (maps Kea leases → NetBox IPAM)
4. Deploy netbox-billing plugin to production NetBox
5. Deploy netbox-stripe-sync with real credentials

## Do Not

- Add billing custom fields to NetBox Tenants
- Design for PPPoE — all new code assumes IPoE/DHCP + Option 82
- Commit live secrets (tokens, passwords, Stripe keys, webhook URLs)
- Restart Kea with active leases (use config-reload via control socket)
- Upgrade NetBox without checking all plugin compatibility (pinned to 4.1.11)
- Cancel Splynx until billing stack is fully live with real Stripe
