# LynxNetStack Ops Guide

Day-to-day reference for operating the ResiBridge ISP stack — what tools exist,
when to use each one, and how to answer the most common operator questions.

---

## Table of Contents

1. [The Stack at a Glance](#the-stack-at-a-glance)
2. [Site Reference](#site-reference)
3. [Jake2 — Your Primary Interface](#jake2--your-primary-interface)
4. [NetBox — Source of Truth](#netbox--source-of-truth)
5. [MCP Servers — Jake's Tool Layer](#mcp-servers--jakes-tool-layer)
6. [Checking a Subscriber](#checking-a-subscriber)
7. [Investigating a Site Outage](#investigating-a-site-outage)
8. [RouterOS / Switch Operations](#routeros--switch-operations)
9. [DHCP and kea-sync](#dhcp-and-kea-sync)
10. [Provisioning a New Subscriber](#provisioning-a-new-subscriber)
11. [Billing](#billing)
12. [When to Use What](#when-to-use-what)

---

## The Stack at a Glance

```
┌───────────────────────────────────────────────────────────────────────┐
│  YOU                                                                  │
│                                                                       │
│   Jake2 WebUI / CLI          PYPR coordinator           NetBox UI     │
│   :8080 (localhost)          :8090 (localhost)    172.27.48.233:8001  │
└────────┬──────────────────────────┬────────────────────────┬──────────┘
         │  natural language        │  route + journal        │ direct edit
         │  queries + audits        │                         │
         ▼                          ▼                         │
┌────────────────────────┐  ┌────────────────────┐           │
│     jake2 MCP layer    │  │  jake2-substrate    │           │
│  22 servers (see §5)   │  │  192.168.110.25:1822│           │
│  – read network state  │  │  evidence journal   │           │
│  – push config (gated) │  └────────────────────┘           │
└────────┬───────────────┘                                    │
         │                                                    │
         ▼                                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        NetBox 4.1.11                                   │
│                    http://172.27.48.233:8001                           │
│  Sites / Devices / Interfaces / IP Prefixes / Cables                  │
│  Tenants (units) / CX-Circuits (subscriber links) / Contacts          │
└────────┬──────────────────────────┬────────────────────────────────────┘
         │                          │
         ▼                          ▼
┌──────────────────┐      ┌──────────────────────────┐
│  BigMac          │      │  Kea DHCP4 (jumpB)        │
│  RouterOS proxy  │      │  127.0.0.1:8000 (loopback)│
│  172.27.226.246  │      │  63 subnets, CGNAT space  │
│  :8081           │      │  100.65.X.0/24             │
└──────────────────┘      └──────────────────────────┘
         │                          │ leases polled by kea-sync
         ▼                          ▼
  Live switch reads          NetBox IPAM (subscriber IPs)
  95 MikroTik CRS           100.65.X.Y/32 per active lease
  1 CCR2116 router
```

### Running services quick-reference

| Service | Address | What it does |
|---|---|---|
| NetBox | `172.27.48.233:8001` | Source of truth for all network objects |
| BigMac | `172.27.226.246:8081` | RouterOS API proxy — all switch reads |
| Prometheus | `172.27.72.179:9090` | Metrics: switches, CPE, OLT |
| Kea DHCP4 | jumpB `127.0.0.1:8000` | DHCP server, 63 CGNAT subnets |
| jake2-substrate | `192.168.110.25:1822` | Evidence journal (Mac Mini) |
| Jake2 WebUI | `localhost:8080` | Jake UI + API (run locally) |
| PYPR coordinator | `localhost:8090` | Intent router / journal inlet |
| Splynx | Live (external) | Legacy billing — do NOT cancel |

---

## Site Reference

Operators use friendly names; everything in code uses the six-digit site code.

| Name | Site ID | Address | Notes |
|---|---|---|---|
| Savoy | `000002` | — | |
| Park 79 | `000003` | — | also "park79" |
| Cambridge | `000004` | — | |
| Essex | `000005` | — | flat pool `100.64.36.0/22` |
| Claiborne | `000006` | — | |
| NYCHA / 2020 Pacific | `000007` | 2020 Pacific St, Brooklyn | largest site |
| Chenoweth | `000008` | — | |
| Euclid | `000011` | — | |
| Longwood | `000012` | — | |
| Londonderry | `000014` | — | |
| Millersville | `000015` | — | |
| Woodlea | `000016` | — | |
| Liberty Terrace | `000017` | — | also "libertyterrace" |
| Findlay | `000018` | — | |
| Lefferts | `000020` | — | |
| Festival Field | `000021` | — | also "festivalfield" |
| Sweetwater | `000022` | — | |
| Atlantis | `000023` | — | |

Device naming: `XXXXXX.BBB.TYPE##` — e.g. `000007.001.SW01` (site 7, building 1, first switch).
Relay IPs: `100.65.X.11` for site X's primary switch (e.g. `100.65.7.11` for NYCHA).

---

## Jake2 — Your Primary Interface

Jake2 is your NOC assistant. You ask it questions in plain English and it
pulls live data from NetBox, BigMac, Prometheus, Kea, and vendor controllers.

### Start Jake2

```bash
cd ~/projects/LynxNetStack/jake2
source .venv/bin/activate
./jake --serve
```

Then open `http://localhost:8080` in a browser.

```
┌─────────────────────────────────────────────────────────────────┐
│  Jake2                                         [JakeQuery tab]  │
│─────────────────────────────────────────────────────────────────│
│                                                                 │
│  Ask anything about the network:                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  how many customers online at nycha                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Result:                                                │   │
│  │  Site 000007 — 84/104 units online (81%)                │   │
│  │  Preferred MCP: site_observability_mcp                  │   │
│  │  ...                                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### CLI mode

```bash
.venv/bin/python -m core.jake_query "what's going on at essex"
```

### What you can ask

| Question type | Example | What Jake does |
|---|---|---|
| Site status | `"what's the status at savoy"` | Pulls online count, alerts, recent faults |
| Subscriber lookup | `"find unit 4A at nycha"` | NetBox tenant + CX-Circuit + current IP |
| Device info | `"tell me about 000007.001.SW01"` | Switch interfaces, uplinks, online CPEs |
| DHCP leases | `"what IP does unit 12B at cambridge have"` | Kea lease → NetBox IPAM |
| Alert summary | `"any active alerts"` | Alertmanager current firing alerts |
| MCP routing | `"which mcp for vlan issues at nycha"` | Returns the right server to attach |
| Audit | `"run an audit on chenoweth"` | Generates NYCHA audit workbook |

### Understanding layer (intent confidence)

Jake parses your input through an LLM (Ollama, `gemma4:26b`) to extract
structured intent before executing anything. If confidence is below threshold:

- **High confidence (≥ 0.85)**: executes immediately
- **Medium (≥ 0.65)**: executes with a note about the interpretation
- **Low (≥ 0.40)**: asks for clarification before acting
- **Below 0.40**: returns `unclear` — rephrase or be more specific

If Jake misunderstands a question, rephrase with the site name or device
name explicitly: `"how many online at 000007"` instead of `"how many online"`.

---

## NetBox — Source of Truth

Everything authoritative lives in NetBox. Jake reads from it; the UI lets
you write to it directly.

**URL:** `http://172.27.48.233:8001`

### Key object hierarchy

```
Site (000007)
  └─ Device (000007.001.SW01)  — naming: XXXXXX.BBB.TYPE##
       └─ Interface (ETH3)     — naming: ETH{N}  (not ether3)
            └─ Cable
                 └─ Circuit Termination Z
                      └─ CX-Circuit (000007.001.1B)
                           └─ Tenant (unit 1B)
                                └─ Contact (subscriber name/email/phone)
```

### Naming conventions

| Object | Format | Example |
|---|---|---|
| Device | `XXXXXX.BBB.TYPE##` | `000007.001.SW01` |
| Interface | `ETH{N}` | `ETH3` (not `ether3`) |
| CX-Circuit | `XXXXXX.BBB.UNIT` | `000007.001.1B` |
| Tenant Group | six-digit.building | `000007.001` |
| Tenant | unit label | `1B` |

**Note:** Device renaming to `XXXXXX.BBB.TYPE##` format is in progress.
Devices in NetBox may still have old names — the classifier and Jake both
handle both forms.

### Common NetBox lookups

**Find a subscriber's device:**
```
DCIM → Devices → search "000007.001"
```

**Find who is on a specific switch port:**
```
DCIM → Devices → [switch name] → Interfaces → ETH3 → Connected Endpoints
→ follow cable → Circuit Termination → Circuit → Tenant
```

**Check a subscriber IP:**
```
IPAM → IP Addresses → filter by "100.65.7."
→ description: "kea-sync | circuit=CX-0042 | mac=..."
```

**Add a new subscriber:**
See [Provisioning a New Subscriber](#provisioning-a-new-subscriber).

---

## MCP Servers — Jake's Tool Layer

Jake's MCP servers are the tools Jake (and Claude Code) use to read live
network state. You do not call these directly in normal ops — Jake routes
to the right one automatically. But knowing what exists helps you understand
what Jake can and cannot do.

```
Group                    Servers                          What it reads
─────────────────────────────────────────────────────────────────────────
frontdoor                jake_frontdoor_mcp               Routes NL queries → Jake actions
core_ops                 jake_ops_mcp                     Full correlations: NetBox+RouterOS+TAUC+Vilo
inventory_observability  netbox_readonly_mcp              NetBox devices/circuits/IPs (read-only)
                         alertmanager_readonly_mcp        Prometheus Alertmanager
                         bigmac_readonly_mcp              RouterOS switch state via BigMac proxy
                         site_observability_mcp           Per-site online count, fault summary
wireless_transport       cnwave_exporter_readonly_mcp     Cambium cnWave RF metrics
vendor_controllers       tauc_mcp                         TP-Link OLT/ACS controller
                         vilo_mcp                         Vilo mesh AP portal
                         tplink_access_mcp                TP-Link direct access
                         vilo_access_mcp                  Vilo AP direct access
routeros_troubleshooting routeros_dispatch_mcp            Routes RouterOS questions to sub-servers
                         routeros_access_mcp              Subscriber access port state
                         routeros_switching_mcp           Bridge VLAN, MAC table, STP
                         routeros_routing_mcp             Routes, BGP/OSPF, ARP
                         routeros_platform_mcp            Hardware health, resources
                         routeros_ops_mcp                 Operational commands
                         routeros_wireless_mcp            Wireless client state
swos_troubleshooting     swos_switching_mcp               SwOS/CSS switching (CRS non-RouterOS)
```

### Attaching MCP servers to Claude Code

Add to your Claude Code MCP config (`~/.claude.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "jake_frontdoor": {
      "command": "python",
      "args": ["/path/to/LynxNetStack/jake2/mcp/jake_frontdoor_mcp.py"]
    },
    "jake_ops": {
      "command": "python",
      "args": ["/path/to/LynxNetStack/jake2/mcp/jake_ops_mcp.py"]
    }
  }
}
```

For most NOC work, `jake_frontdoor_mcp` + `jake_ops_mcp` is enough.
Load additional servers when investigating specific subsystems (e.g. add
`routeros_switching_mcp` for a VLAN trace).

---

## Checking a Subscriber

### Via Jake (fastest)

```
"find unit 12B at cambridge"
"what IP does unit 4A nycha have"
"is unit 1B at essex online"
```

Jake returns: tenant details, CX-Circuit, current DHCP lease IP, CPE type,
and whether the circuit appears up.

### Via NetBox (direct)

1. IPAM → IP Addresses → search the subscriber IP or MAC
2. Or: DCIM → Circuits → search CX-Circuit ID (e.g. `000004.001.12B`)

### Via Kea (last-resort, on jumpB)

```bash
ssh jumpB
/opt/kea-dhcp/list-leases | python3 -m json.tool | grep -A 10 '"giaddr": "100.65.4.11"'
```

This dumps all active leases for a subnet. Useful when NetBox IPAM is stale
and you need the authoritative current lease.

### Reading a Kea lease record

```json
{
  "ip-address": "100.65.4.142",        ← subscriber's current IP
  "hw-address": "aa:bb:cc:dd:ee:ff",   ← subscriber CPE MAC
  "giaddr": "100.65.4.11",             ← relay = primary switch for site 000004
  "valid-lft": 86400,                  ← lease length in seconds (24h)
  "user-context": {
    "ISC": {
      "relay-agent-info": {
        "circuit-id": "6574686572333a3230"   ← hex for "ether3:20" = ETH3, VLAN 20
      }
    }
  }
}
```

Decode the circuit-id:
```bash
python3 -c "import binascii; print(binascii.unhexlify('6574686572333a3230').decode())"
# ether3:20  →  switch port ETH3, VLAN 20
```

---

## Investigating a Site Outage

### Step 1 — Jake summary

```
"what's the status at nycha"
"any active alerts at 000007"
```

If Jake returns a healthy summary but field says there's an outage, proceed
to step 2.

### Step 2 — Check Prometheus / Alertmanager

```
http://172.27.72.179:9090
```

Useful queries:

```promql
# Is the primary switch reachable?
up{job="mikrotik", instance="192.168.44.7"}

# OLT online CPE count at a site
tplink_olt_online_onus{site="000007"}

# Subscriber online metric (Splynx PPPoE sessions, legacy)
splynx_customer_online
```

### Step 3 — RouterOS switch state via BigMac

Ask Jake:
```
"check arp table on 000007.001.SW01"
"show mac table on 000007.001.SW01 port ETH3"
"what vlan is ether3 on 000007.001.SW01"
```

Or use `bigmac_readonly_mcp` directly if Jake is unavailable.

### Step 4 — Kea lease check on jumpB

If DHCP is suspect:
```bash
ssh jumpB
# Count leases for a subnet (site 7 = 100.65.7.0/24)
/opt/kea-dhcp/list-leases | python3 -c "
import json, sys
leases = json.load(sys.stdin)
site7 = [l for l in leases if l.get('ip-address','').startswith('100.65.7.')]
print(f'{len(site7)} active leases for site 000007')
"
```

If lease count is zero after a Kea restart, clients need to renew:
```bash
# Do NOT restart kea-dhcp4. Reload config only:
curl -s -X POST http://127.0.0.1:8000/ \
  -H 'Content-Type: application/json' \
  -d '{"command":"config-reload","service":["dhcp4"]}'
```

### Step 5 — OLT check (TP-Link)

For sites using GPON (has `uses_olt: true` in site profile):
```
"check OLT status at savoy"
"how many ONUs online at 000002"
```

Jake routes this to `tauc_mcp` or `tplink_access_mcp`.

### Outage decision tree

```
Site reported down
│
├─ Jake shows alerts? ──yes──▶ Check Alertmanager, follow alert runbook
│
├─ Prometheus shows switch unreachable? ──yes──▶ Physical/power issue at site
│
├─ Switch reachable, but subscribers down?
│   ├─ DHCP lease count = 0? ──yes──▶ Kea issue (check docker ps, logs)
│   ├─ Leases exist, no traffic? ──▶ Routing/VLAN issue — check RouterOS
│   └─ OLT site: ONUs offline? ──▶ Fiber cut or OLT power — check tauc_mcp
│
└─ Single unit down, rest of site ok?
    └─ Check that unit's lease, CPE MAC, cable in NetBox
```

---

## RouterOS / Switch Operations

All switch reads go through **BigMac** (`172.27.226.246:8081`) — a RouterOS
API proxy that handles authentication and rate limiting for all 95 switches.
Do not SSH to switches directly for reads; use BigMac or the MCP servers.

### Common operations via Jake

```
# ARP / MAC lookup
"find MAC aa:bb:cc:dd:ee:ff"
"show arp table on 000007.001.SW01"

# Interface state
"what's connected to ETH5 on 000003.001.SW01"
"show interface stats for 000004.001.SW01"

# VLAN
"show vlan config on 000007.001.SW01"
"what VLANs does ETH3 carry at nycha"

# Routing
"show routes on CCR2116"
"BGP status"
```

### Config changes (ssh_mcp — approval-gated)

`ssh_mcp` can push config to switches but requires explicit operator approval
before executing. Never used for reads — use BigMac for those.

**Workflow:**
1. Jake or an MCP tool proposes a change
2. The change is staged and shown to you for review
3. You approve → `ssh_mcp` pushes to the device
4. Jake logs the change to the substrate evidence journal

### Hardware offload reminder

**HW offload is OFF site-wide on all NYCHA switches.** Do not re-enable it.
This is a permanent network design decision, not a configuration error.

---

## DHCP and kea-sync

### Architecture

```
Subscriber CPE (100.65.X.Y)
    │  DHCP Discover (Option 82: circuit-id, giaddr)
    ▼
MikroTik switch (giaddr = 100.65.X.11)
    │  DHCP relay
    ▼
Kea DHCP4 on jumpB (127.0.0.1:8000)
    │  assigns from pool .41–.250
    ▼
kea-sync (running on jumpB, polls every 60s)
    │  resolves: giaddr → device → interface → cable → CX-Circuit
    ▼
NetBox IPAM: 100.65.X.Y/32 record, linked to CX-Circuit + Tenant
```

### CGNAT subnets

- One `/24` per building: `100.65.X.0/24` where X = site number
- Pool: `.41` to `.250`
- Gateway: `.X.1`
- Relay (primary switch): `.X.11`
- Essex (site 5) exception: flat `100.64.36.0/22`

### kea-sync status check

```bash
ssh jumpB
# If running as systemd:
sudo systemctl status kea-sync
sudo journalctl -u kea-sync -n 50

# If running in Docker:
docker logs kea-sync --tail 50
```

Healthy log line:
```
[INFO] Poll complete: 247 leases processed
```

If you see `[ERROR] Failed to fetch Kea leases` — Kea container may be down:
```bash
jumpB$ docker ps | grep kea
jumpB$ docker logs kea-dhcp4 --tail 30
```

### Manually checking a lease

```bash
ssh jumpB
/opt/kea-dhcp/list-leases | python3 -c "
import json, sys
leases = json.load(sys.stdin)
for l in leases:
    if l.get('hw-address') == 'aa:bb:cc:dd:ee:ff':
        print(json.dumps(l, indent=2))
"
```

---

## Provisioning a New Subscriber

### Full provisioning flow

```
1. Create Tenant Group (if new building)
   NetBox → Tenancy → Tenant Groups → + Add
   Name: "000007.001"  Slug: "000007-001"

2. Create Tenant (unit)
   NetBox → Tenancy → Tenants → + Add
   Name: "1B"  Group: "000007.001"

3. Create Contact
   NetBox → Contacts → + Add
   Name, email, phone

4. Assign Contact to Tenant
   Tenant → Contacts tab → Assign Contact (role: Customer)

5. Create CX-Circuit
   NetBox → Circuits → Circuits → + Add
   CID: "000007.001.1B"
   Provider: Lynxnet
   Tenant: 1B (under 000007.001)
   Commit rate: 100000 (100 Mbps) or per plan

6. Create Circuit Terminations
   Circuit → + Add Termination (Side Z)
   Site: 000007

7. Cable the circuit to the switch interface
   DCIM → Devices → 000007.001.SW01 → Interfaces → ETH3
   → + Connect Cable → Circuit Termination Z (just created)

8. Kea host reservation (optional, for stable IP)
   On jumpB, add to kea-dhcp4.conf:
   {
     "hw-address": "aa:bb:cc:dd:ee:ff",
     "ip-address": "100.65.7.45",
     "user-context": { "circuit-id": "000007.001.1B" }
   }
   Then reload (NOT restart):
   curl -X POST http://127.0.0.1:8000/ -H 'Content-Type: application/json' \
     -d '{"command":"config-reload","service":["dhcp4"]}'
```

### Subscriber gets an IP

Once cabled and DHCP relay is passing Option 82, the subscriber will get an
IP within one DHCP cycle. kea-sync will pick it up within 60 seconds and
create the NetBox IPAM record automatically.

Verify in NetBox:
```
IPAM → IP Addresses → filter "100.65.7."
→ look for kea-sync | circuit=000007.001.1B
```

---

## Billing

### Current state

Billing is **not yet fully live.** Splynx is still the active billing system.
Do NOT cancel Splynx until netbox-stripe-sync is running with real Stripe keys.

```
Current:  Splynx (live, real payments)
Target:   netbox-billing plugin + netbox-stripe-sync + Stripe
Status:   plugins deployed, Stripe in test mode
```

### Components

| Component | Path | Status |
|---|---|---|
| netbox-billing | `billing/netbox-billing/` | Plugin installed in NetBox |
| netbox-contract | `billing/netbox-contract/` | Plugin installed in NetBox |
| netbox-stripe-sync | `billing/netbox-stripe-sync/` | Webhook bridge, test mode |

### netbox-stripe-sync (when live)

```bash
cd billing/netbox-stripe-sync
cp .env.example .env
# Edit .env — add STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, NETBOX_TOKEN
uvicorn app.main:app --port 8083
```

Stripe webhooks → `POST /webhook` → updates NetBox invoice/contract status.

### Objects in NetBox (billing plugin)

```
BillingAccount → Tenant
  └─ Subscription → TariffPlan (e.g. 100 Mbps / $60/mo)
       └─ Invoice (monthly, generated by sync)
```

---

## When to Use What

| Situation | Tool |
|---|---|
| Quick subscriber status | Jake2: `"unit 4A at nycha"` |
| Site-wide outage check | Jake2 + Prometheus |
| Current DHCP leases | Jake → Kea via `site_observability_mcp` |
| Edit subscriber data | NetBox UI directly |
| Push switch config | Jake → `ssh_mcp` (approval required) |
| Read switch state | Jake → `bigmac_readonly_mcp` |
| OLT CPE status | Jake → `tauc_mcp` or `tplink_access_mcp` |
| Vilo mesh AP check | Jake → `vilo_access_mcp` |
| RF / wireless backhaul | Jake → `cnwave_exporter_readonly_mcp` |
| Generate audit workbook | Jake: `"run audit on essex"` |
| Log a work note | PYPR: `"note: renamed SW01 to 000005.001.SW01"` |
| Investigate incident | PYPR → substrate evidence journal |
| Check billing status | NetBox billing plugin (once live) |
| Emergency Kea reload | `ssh jumpB` → curl config-reload command |

### What Jake cannot do (yet)

- Push configuration changes without `ssh_mcp` in the loop and your approval
- Access Splynx directly (legacy billing, no API integration)
- Provision a new subscriber end-to-end (NetBox steps still manual)
- Predict future faults (alerting is reactive, not predictive)
