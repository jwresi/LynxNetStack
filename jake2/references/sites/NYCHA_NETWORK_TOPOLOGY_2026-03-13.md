# NYCHA Network Topology Notes

Date: 2026-03-13  
Scope: Site `000007` NYCHA transport, roof-switch, Siklu, cnWave, and access-switch topology as learned from live network interrogation, NetBox, and deterministic Jake data.

## Summary

This site is not a flat network. The active design is a layered transport/distribution fabric:

1. Headend / main router at `728 E New York Ave`
2. Linear Siklu transport chain
3. Roof aggregation switches (`RFSW01`)
4. cnWave distribution side on roof-switch `sfp4`
5. Building access switches
6. Customer CPEs on VLAN 20, management on VLAN 10, special handoffs on VLAN 30

The Siklu ring is **not yet closed**. The active chain is linear today.

## Core Site Identity

- Site ID: `000007`
- Main router: `000007.055.R01`
- Main router IP: `192.168.44.1`

Current trustworthy site customer count after cleanup:
- `148` active customers
- Counting method: PPP active sessions on `000007.055.R01`

## VLAN Roles

- VLAN `10`: management
- VLAN `20`: customer/service
- VLAN `30`: special handoff / elevator / site-specific equipment

## Siklu Transport Chain

The active chain is:

1. `728 E NY` -> `955 Rutland`
   - `192.168.44.2`
   - `192.168.44.3`

2. `955 Rutland` -> `1145 Lenox`
   - `192.168.44.4`
   - `192.168.44.5`

3. `1145 Lenox` -> `725 Howard`
   - `192.168.44.6`
   - `192.168.44.7`

Two more sites are planned to close the ring, but they are not installed yet.

### Current Siklu Health

- `.2` (`728 E NY - 955 Rutland`) is the unhealthy side
  - login works
  - management plane is unstable
  - repeated `eth0` link flap events were observed
- `.3` is materially healthier
- Downstream Siklu nodes `.4/.5/.6/.7` are reachable

Interpretation:
- The transport chain is degraded, not uniformly dead
- `.2` is a priority fault

## Roof Switches

### `000007.004.RFSW01`
- Address: `1145 Lenox Rd, Brooklyn, NY 11212`
- IP: `192.168.44.15`
- Model: `CRS305-1G-4S+IN`
- Local handoff:
  - `ether1` = VLAN `10` untagged (local technician management)

### `000007.053.RFSW01`
- Address: `725 Howard Ave, Brooklyn, NY 11212`
- IP: `192.168.44.16`
- Model: `CRS305-1G-4S+IN`
- Local handoff:
  - `ether1` = VLAN `10` untagged (local technician management)

### `000007.058.RFSW01`
- Address: `955 Rutland Rd, Brooklyn, NY 11212`
- IP: `192.168.44.14`
- Model: `CRS305-1G-4S+IN`
- Local handoff:
  - `ether1` = VLAN `30` untagged

### Intended SFP Roles On Roof Switches

General intended roles:

- `sfp1` = upstream trunk
- `sfp2` = down to customer/building switches
- `sfp3` = trunk to next site / wireless bridge side
- `sfp4` = Cambium cnWave side

This is the intent model. Some live site behavior had drifted from it.

### Roof-Switch Cleanup Completed

All three roof switches were hardened successfully on `sfp1-4`:

- `ingress-filtering=yes`
- `frame-types=admit-only-vlan-tagged`

Validated on:
- `000007.004.RFSW01`
- `000007.053.RFSW01`
- `000007.058.RFSW01`

Result:
- no management loss
- no downstream switch loss
- site outliers dropped from `41` to `4`

## cnWave Topology

### Working POP anchors

#### `1145 Lenox Ave V5000`
- IP: `192.168.44.19`
- Role: `POP`
- E2E: connected
- Layer 2 bridge: enabled
- Active links: non-zero

#### `725 Howard V5000`
- IP: `192.168.44.20`
- Role: `POP`
- E2E: connected
- Layer 2 bridge: enabled
- Active links: non-zero

### Problem node

#### `728 E New York V5000`
- IP: `192.168.44.152`
- Last known good management state:
  - Role: `DN`
  - E2E: `Not Connected`
  - Layer 2 bridge: `Disabled`
  - Active links: `0`
- Intended role if directly off the router:
  - likely `POP`

This node was previously plugged in and caused major network instability.

### cnWave Ethernet-side learning

On active roof switches, `sfp4` is not a one-host management link. It carries a bridged cnWave domain with multiple VLANs visible:

- VLAN `10`
- VLAN `20`
- VLAN `30`

This was proven by live bridge-host counts on `sfp4` before cleanup.

Interpretation:
- `sfp4` must be treated as a strict trunk
- but it is still a service-carrying bridged domain, not just radio management

## Main Router Special Case: `.152`

Router-facing port for `728 E New York V5000`:
- Router: `000007.055.R01`
- Port: `sfp-sfpplus10`
- Port comment: `Fenimore V5000`

Current live state:
- `frame-types=admit-only-vlan-tagged`
- `ingress-filtering=yes`
- `pvid=10`

Current bridge-host evidence on that port:
- only local router MACs
- no external radio MAC learned there now

Interpretation:
- management to `.152` was likely lost because the port stopped carrying native VLAN 10 the way the disconnected node expected
- this did **not** break the router or the working POPs

## Building Blocks Frequently Investigated

These building switch blocks were confirmed reachable while troubleshooting customer outages:

- `000007.025`
- `000007.027`
- `000007.035`
- `000007.036`
- `000007.038`
- `000007.058`

This means the dominant failure domain was not “building switch dead,” but transport/radio/recovery above or beside them.

## UDM Outlier

- Device: `000007.056.UDM01`
- IP: `192.168.44.210`
- It is a Ubiquiti UDM Pro with WAN failover between ResiBridge and Starlink.

Observed behavior:
- ARP complete on VLAN 10
- alert flaps tied to management reachability

Interpretation:
- likely asymmetric reply path / policy routing issue during failover
- not strong evidence of duplicate IP use

## What Was Proven Tonight

1. Roof-switch permissive trunking was a real site-wide issue.
2. Tightening those roof-switch trunks was safe and materially reduced site outliers.
3. The Siklu chain is linear, not closed.
4. `.2` on the Siklu side is unstable and likely suffering local Ethernet/PoE/copper issues.
5. `.152` is not in the same functional state as the working cnWave POPs.
6. `.152` should not be treated as a healthy reference node.

## Remaining Priority Faults

1. Siklu `192.168.44.2`
2. `728 E New York V5000` `192.168.44.152`
3. `1640 Sterling Pl V2000`
4. `000007.056.UDM01`

## GNS3 Modeling Guidance

To model this in GNS3, use:

### Layer 1/2 objects
- 1 MikroTik main router (`000007.055.R01`)
- 3 Siklu point-to-point segments in a chain
- 3 roof aggregation switches (`RFSW01`)
- cnWave POP nodes at:
  - `1145 Lenox`
  - `725 Howard`
- cnWave problem DN/POP candidate at:
  - `728 E New York`
- downstream building access-switch blocks hanging from the roof switches

### VLAN assumptions
- VLAN 10 = management
- VLAN 20 = customer
- VLAN 30 = special handoff

### Trunk assumptions
- roof-switch `sfp1-4` should be modeled as strict tagged trunks
- `ether1` on each roof switch should preserve the site-specific untagged handoff:
  - `1145 Lenox`: VLAN 10
  - `725 Howard`: VLAN 10
  - `955 Rutland`: VLAN 30

### Exception notes
- `.152` should be modeled as an out-of-state node until corrected
- `.2` should be modeled as a degraded Siklu endpoint with intermittent local Ethernet instability

## Confidence

High confidence:
- Siklu chain layout
- roof-switch identities and roles
- VLAN roles
- working cnWave POP state for `.19` and `.20`
- `.152` being misaligned with the working POPs

Medium confidence:
- exact cnWave service/VLAN behavior behind every `sfp4` at every site
- exact final intended role of `.152` without a working live config baseline from that node in service
