# LynxNetStack Architecture

## System Overview

LynxNetStack is a purpose-built ISP management platform for ResiBridge, replacing Splynx with an open-source stack. It manages subscriber identity, DHCP leases, billing, CPE inventory, and network operations for 63 NYCHA buildings in Brooklyn.

## Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OPERATOR INTERFACES                          │
│  LynxMSP (CRM)          Provisioner (Tech UI)     Jake2 WebUI       │
│  FastAPI + React         Flask + React            FastAPI + React    │
│  :8000/:3002             :5001/:3001              :8080              │
└──────────────┬──────────────────┬──────────────────┬────────────────┘
               │                  │                  │
               ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           NetBox 4.1.11                             │
│              http://172.27.48.233:8001                              │
│                                                                     │
│  SUBSCRIBER IDENTITY (standard objects):                            │
│    Tenant Group (building) → Tenant (unit)                          │
│    → CX-Circuit → cable → switch interface                          │
│    → Contact (name/email/phone) via contact-assignment              │
│                                                                     │
│  BILLING (plugin objects, separate from identity):                  │
│    BillingAccount → Tenant                                          │
│    Subscription → BillingAccount + TariffPlan                       │
│    Invoice → BillingAccount                                         │
│                                                                     │
│  NETWORK (standard objects):                                        │
│    Sites, Devices, Interfaces, IP Prefixes, IP Addresses            │
│    CPE inventory (netbox_inventory plugin)                          │
└──────────┬──────────────────────────────────────┬───────────────────┘
           │                                      │
           ▼                                      ▼
┌──────────────────────┐              ┌───────────────────────────────┐
│     Kea DHCP4        │              │    netbox-stripe-sync         │
│  172.27.28.50        │              │    :8083                      │
│                      │              │                               │
│  Option 82 circuit-id│              │  Stripe webhooks → NetBox     │
│  Host reservations   │              │  invoice/contract status      │
└──────────┬───────────┘              └───────────────────────────────┘
           │ leases (REST API)                    ▲
           ▼                                      │ webhooks
┌──────────────────────┐              ┌───────────────────────────────┐
│     kea-sync         │              │         Stripe                │
│                      │              │  (test mode until cutover)    │
│  Poll every 60s      │              └───────────────────────────────┘
│  circuit-id → tenant │
│  → upsert NetBox IP  │
└──────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       NETWORK ACCESS LAYER                          │
│                                                                     │
│  BigMac (RouterOS API proxy)  http://172.27.226.246:8081            │
│  95 MikroTik CRS switches     192.168.44.0/24 mgmt                 │
│  1 CCR2116 router             192.168.44.1                          │
│  Subscriber VLANs             10.0.8.0/13                           │
│                                                                     │
│  Jake2 MCP servers read live data via BigMac                        │
│  ssh_mcp pushes config changes (approval-gated)                     │
│  tikfig generates RouterOS configs from NetBox + Jinja2             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       OBSERVABILITY                                 │
│  Prometheus  http://172.27.72.179:9090                              │
│  mikrotik-exporter, switchos-exporter, tplink-olt-exporter          │
│  splynx_customer_online metric (444 active PPPoE subscribers)       │
└─────────────────────────────────────────────────────────────────────┘
```

## Subscriber Identity Data Flow

```
Splynx (legacy, still live)
  │
  ├─ PPPoE sessions → freeRADIUS → subscriber online/offline
  └─ Customer records → migrate to NetBox

NetBox (target state)
  Tenant Group "000007.001" (104 Tapscott, Brooklyn)
    └─ Tenant "1B"
         └─ CX-Circuit "000007.001.1B"
              ├─ provider: Lynxnet
              ├─ commit_rate: 100000 (100 Mbps)
              ├─ Contact: "Jane Doe" <jane@example.com>  [role=Customer]
              └─ termination_Z ──cable──> 000007.001.SW01.ETH3
                                               │
                                               └─ ether3 on physical switch
                                                    │
                                                    └─ CPE (TP-Link HC220-G5)
                                                         └─ DHCP lease: 10.0.8.45
                                                              (written by kea-sync)
```

## Option 82 / IPoE Identity Resolution

```
DHCP DISCOVER with Option 82
  circuit-id = "ether3:20"  (RouterOS 7.21+ format: <iface>:<vlan>)
  giaddr = 192.168.44.42    (switch management IP on VLAN 10)

  kea-sync resolution:
    1. giaddr 192.168.44.42
       → NetBox device with primary_ip4 = 192.168.44.42
       → "000007.001.SW01"

    2. circuit-id "ether3:20" → interface "ETH3"
       → NetBox interface ETH3 on 000007.001.SW01

    3. cable ETH3 → circuit termination Z
       → CX-Circuit "000007.001.1B"
       → Tenant "1B" in group "000007.001"

    4. Upsert IP 10.0.8.45/32 in IPAM
       → linked to Tenant "1B"
```

## Jake2 Two-Layer Architecture

```
Raw operator language
  │
  ▼
core/intent_parser.py  (understanding layer)
  │  ← never touches live data
  │  ← returns structured IntentSchema JSON
  ▼
core/dispatch.py  (confidence gate)
  │  ← thresholds from config/intent_parser.yaml
  │  ← blocks low-confidence intents from reaching execution
  ▼
core/query_core.py  (execution layer)
  │  ← accepts only structured intent
  │  ← never receives raw natural language
  │  ← never calls LLM directly
  ├─→ mcp/jake_ops_mcp.py → BigMac, NetBox, Prometheus
  ├─→ mcp/bigmac_readonly_mcp.py → RouterOS live reads
  ├─→ mcp/tauc_mcp.py → TP-Link OLT
  └─→ audits/ → workbook generation
```

## Billing Architecture

```
Stripe (payment processor)
  │
  │ webhooks (invoice.paid, subscription.updated, etc.)
  ▼
netbox-stripe-sync (:8083)
  │
  │ writes status to
  ▼
NetBox + netbox-contract plugin
  │  Invoice.status, Contract.status
  │
  │ BillingAccount linked to
  ▼
NetBox Tenant (subscriber identity)
  │
  └─ Subscription → TariffPlan (plan tier, price)
```

## VLAN Assignments

| VLAN | Name | Purpose |
|------|------|---------|
| 10 | Management | Switch/router management |
| 20 | Customer | Subscriber DHCP (IPoE target) |
| 30 | Fairstead | Property management handoff (NOT a generic security VLAN) |
| 55 | Recovery | NetInstall / provisioning recovery |

## Migration State (as of 2026-04-30)

All 444 subscribers are still on PPPoE via Splynx/freeRADIUS. The IPoE migration is blocked on:
1. Kea DHCP4 deployment on 172.27.28.50
2. Full CX-Circuit population in NetBox (Priority 1)
3. Switch firmware: 8 devices on 7.14.x need upgrading to 7.21.3+

Do not change `Customer_Auth_Type_Deployment` on site 000007 from `"1 - PPPOE"` to `"2 - DHCP"` until a building cutover is complete.
