# LynxNetStack

LynxNetStack is the unified platform monorepo for **ResiBridge** — a WISP/MDU operator serving NYCHA public housing in Brooklyn, NY. It replaces Splynx with a purpose-built open-source stack.

## What's In This Repo

| Component | Path | Purpose |
|-----------|------|---------|
| **Jake2** | `jake2/` | Network intelligence engine: natural-language queries, deterministic audits, MCP servers for BigMac/TAUC/Vilo/RouterOS |
| **Provisioner** | `provisioner/` | Tech-facing provisioning UI: port map, CSV batch provisioning, MNDP discovery, audit log |
| **Tikfig** | `tikfig/` | NetBox → Jinja2 → RouterOS config generation for switches and routers |
| **ssh_mcp** | `ssh_mcp/` | Approval-gated SSH to RouterOS devices (propose → approve → execute + audit) |
| **LynxMSP** | `lynxmsp/` | Operator-facing CRM UI (FastAPI + React), wired to NetBox as record backend |
| **netbox-billing** | `billing/netbox-billing/` | NetBox plugin: BillingAccount, Subscription, Invoice, Stripe integration |
| **netbox-stripe-sync** | `billing/netbox-stripe-sync/` | FastAPI sidecar: Stripe webhooks → NetBox contract/invoice status |
| **netbox-contract** | `billing/netbox-contract/` | Open-source NetBox plugin: Contract + Invoice models |
| **kea-sync** | `kea-sync/` | Kea DHCP4 lease poller → NetBox IPAM IP sync via circuit-id/Option 82 |
| **netbox-scripts** | `netbox-scripts/` | Migration and provisioning scripts: CX-Circuit population, IPAM seed |
| **deploy** | `deploy/` | Docker Compose, systemd units, Ansible playbooks |
| **docs** | `docs/` | Architecture, runbooks, API reference |

## Production Network (NYCHA 000007)

- **NetBox:** `http://172.27.48.233:8001`
- **BigMac (RouterOS API proxy):** `http://172.27.226.246:8081`
- **Prometheus:** `http://172.27.72.179:9090`
- **Kea DHCP4 (target):** `172.27.28.50`
- **Router:** 000007.055.R01 — CCR2116-12G-4S+ at 192.168.44.1
- **Switches:** 95 MikroTik CRS devices across 63 buildings
- **Subscribers:** ~444 active (migrating PPPoE → IPoE/DHCP relay)

## NetBox Subscriber Data Model

```
Tenant Group  =  Building        (e.g. "000007.001" → "104 Tapscott")
Tenant        =  Unit/subscriber (e.g. "1B", group=000007.001)
Circuit       =  CX-Circuit      (provider=Lynxnet, type=CX-Circuit)
                   linked to Tenant
                   termination_z → cable → switch interface (e.g. 000007.001.SW01.ETH3)
Contact       =  Subscriber name/email/phone
                   assigned to Circuit via contact-assignment (role=Customer)
```

Subscriber identity lives in standard NetBox objects. Billing attaches via `BillingAccount → Tenant` (netbox-billing plugin).

## Quick Start

```bash
git clone https://github.com/jwresi/LynxNetStack.git
cd LynxNetStack

# Jake2 (network intelligence)
cd jake2
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
cp config/.env.example config/.env  # fill in real values
./jake --serve

# Provisioner (switch provisioning UI)
cd provisioner
make up  # frontend :3000, backend :5001

# Tikfig (config generator)
cd tikfig
cp config.example.yml config.yml
pip install -r requirements.txt && python app.py

# ssh_mcp
cd ssh_mcp
cp config/ssh_mcp.example.json config/ssh_mcp.json
pip install -e . && python -m ssh_mcp.server

# Kea sync
cd kea-sync
pip install -r requirements.txt
python lease_poller.py
```

## Build Status

| Component | State |
|-----------|-------|
| NetBox subscriber model | Proof-of-concept — 6 CX-Circuits, needs full NYCHA scale |
| IPoE / Kea migration | Not started — all 444 subscribers still on PPPoE |
| netbox-billing | Built, not deployed to production NetBox |
| netbox-stripe-sync | Built, not deployed with real credentials |
| Jake2 | Live and production |
| Splynx | Live, active billing — **do not cancel** |

## Architecture Constraints

1. Subscriber identity lives in standard NetBox (Circuit → Tenant → Contact) — never in billing plugin fields
2. Switch interface naming in NetBox: `ETH{N}` format (ether1 → ETH1)
3. All CX-Circuits use provider=`Lynxnet`
4. Kea circuit-id format (RouterOS 7.21+): `<interface>:<vid>` (e.g. `ether3:20`)
5. DHCP unicast renew has no circuit-id — use Kea host reservations
6. Hardware offload is OFF site-wide on all NYCHA switches
7. NetBox pinned to 4.1.11 — check plugin compatibility before upgrading
8. Do not cancel Splynx until netbox-billing is confirmed working end-to-end

## Contributing

See `AGENTS.md` for coding standards. See `docs/architecture/` for system design.

PRs must include: description, how to verify, and screenshots for UI changes.
