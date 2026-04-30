# AGENTS.md — LynxNetStack Repository Guidelines

## Repo Layout

```
LynxNetStack/
  jake2/          # Network intelligence engine (Python, two-layer architecture)
  provisioner/    # Switch provisioning UI (Flask + React)
  tikfig/         # Config generator (Flask + Jinja2)
  ssh_mcp/        # Approval-gated SSH MCP server
  lynxmsp/        # Operator CRM (FastAPI + React)
  billing/
    netbox-billing/       # NetBox plugin
    netbox-stripe-sync/   # Stripe webhook sidecar
    netbox-contract/      # Open-source NetBox Contract plugin
    scripts/              # Billing migration/seed scripts
  kea-sync/       # Kea DHCP lease → NetBox IP sync
  netbox-scripts/ # NetBox population scripts (CX-Circuits, IPAM)
  deploy/         # Docker Compose, systemd, Ansible
  docs/           # Architecture, runbooks, API reference
```

## Core Architectural Rules

1. **Subscriber identity lives in standard NetBox — never in billing plugin fields.**
   Model: `Tenant Group` (building) → `Tenant` (unit) → `CX-Circuit` (service) → `termination_z` → switch interface.
   Billing attaches via `BillingAccount → Tenant` (netbox-billing), kept completely separate.

2. **Switch interface naming in NetBox uses `ETH{N}`** (ETH1, ETH3 etc.).
   RouterOS uses `ether{N}`. The mapping is direct: ether1=ETH1. Use ETH naming when creating circuit termination → interface links.

3. **All CX-Circuits use provider=Lynxnet** (id=9 in production NetBox).

4. **Do not design for PPPoE.** All new code assumes IPoE/DHCP + Option 82 circuit-id identity.

5. **Do not merge Jake2's understanding and execution layers** — strictly separated per jake2/AGENTS.md.

6. **Do not restart Kea with active leases** — use `config-reload` via the control socket.

7. **Do not upgrade NetBox without checking all plugin compatibility first** — pinned to 4.1.11.

## Jake2 Specific Rules

- `core/` may depend on local code and local data contracts only — never on RAG or training assets
- `mcp/` may depend on runtime services and config secrets through explicit configuration
- `agents/` may depend on model runtime services only
- `audits/` may depend on deterministic core + explicit runtime adapters + local artifacts
- Prohibited: `from module import *`, `sys.path` mutation, hardcoded home-dir paths, live secrets in repo

## Provisioner Specific Rules

- Customer access ports: `edge=yes`, `horizon=1`, admit only untagged; BPDU-Guard; Loop-Protect; PoE disabled
- VLAN 10=management, 20=customer/subscriber, 30=Fairstead, 55=recovery
- Do not expose TFTP or DHCP to the public internet

## Billing Rules

- Never store subscriber identity in billing plugin models
- Do not go live with Stripe in production without verifying test-mode transactions end-to-end
- Do not cancel Splynx until netbox-billing is confirmed working end-to-end with real Stripe
- Import Splynx Stripe customer IDs into `BillingAccount.stripe_customer_id` before cutover

## Coding Style

- Python: 4-space indent, snake_case for modules/functions, PascalCase for classes
- React/TS: 2-space indent, PascalCase for components, camelCase for hooks
- Use Black formatting for Python; keep API routes consistent with existing patterns
- Commit messages: verb-led, sentence case (e.g. "Add kea lease poller")
- PRs: concise summary, how to verify, screenshots for UI changes

## Secrets

- Never commit live tokens, passwords, API keys, webhook URLs, or TLS certs
- Use `.env.example` / `config.example.*` with placeholder documentation only
- Jake2 secrets: `jake2/config/.env`
- Provisioner secrets: `provisioner/.env`
- ssh_mcp secrets: `ssh_mcp/config/ssh_mcp.json`
- Billing secrets: `billing/netbox-billing/.env` and `billing/netbox-stripe-sync/.env`
