# Per-Customer VLAN Isolation Rollout

This document describes the target access design for isolating every customer behind a dedicated VLAN, using Savoy (`000002`) as the reference site.

The goal is to eliminate:

- customer-to-customer Layer 2 visibility
- rogue DHCP impact across subscribers
- private LAN leakage (`192.168.88.0/24`, `192.168.0.0/24`, etc.) across the shared access network

This design assumes:

- TP-Link OLTs at the building edge
- CNWave or similar wireless backhaul acting as a transparent Layer 2 bridge
- MikroTik at the aggregation/router layer

## Summary

Do not run customer access as one flat bridge.

Instead:

1. Assign each ONU/customer a dedicated VLAN on the OLT.
2. Carry those VLANs across the mesh/backhaul as a tagged trunk.
3. Terminate each customer VLAN on the MikroTik.
4. Serve DHCP on the customer VLAN interface, not on one shared bridge.
5. Keep infrastructure management on a separate management VLAN/subnet.

## Why This Is Needed

Savoy proved the current failure mode:

- `BR-CGNAT` on `000002.R1` is a flat bridge with `vlan-filtering=no`
- all building/customer uplinks are in the same Layer 2 domain
- DHCP for `192.168.55.0/24` is bound directly to that bridge
- OLT isolation (`port-isolate`, `onu-isolate`) was already enabled
- private customer LANs were still leaking upstream because the aggregation layer remained flat

Conclusion:

- OLT isolation is necessary but not sufficient
- the real architectural fix is per-customer VLAN segmentation

## Target Design

### Access Layer

Each customer ONU gets one unique service VLAN.

Examples:

- Building 1, ONU 4 -> VLAN `1004`
- Building 3, ONU 12 -> VLAN `3012`
- Building 5, ONU 4 -> VLAN `5004`
- Building 7, ONU 15 -> VLAN `7015`

The OLT maps each ONU to its assigned service VLAN.

### Transport Layer

The CNWave/backhaul link carries a tagged trunk, not one flat shared customer bridge.

The mesh does not need to make access decisions. It only needs to pass VLAN tags intact.

### Aggregation Layer

The MikroTik terminates each customer VLAN as a separate interface.

Each customer VLAN gets:

- its own L3 interface
- its own DHCP scope
- its own policy/NAT treatment

### Management Layer

OLT management and infrastructure must not remain in the customer access VLANs.

Use a dedicated management VLAN/subnet per site or per transport domain.

## VLAN Numbering Standard

Use a deterministic numbering scheme based on site/building and ONU.

Recommended format:

- `BBOO`

Where:

- `BB` = building number or OLT number
- `OO` = ONU ID zero-padded to 2 digits if needed

Examples:

- Building 1 ONU 4 -> `1004`
- Building 1 ONU 16 -> `1016`
- Building 5 ONU 4 -> `5004`
- Building 7 ONU 3 -> `7003`

If a site has more ONUs than fit cleanly in that pattern, expand to:

- `SBBNN`

Where:

- `S` = site group digit if needed
- `BB` = building/OLT
- `NN` = ONU

The important rule is consistency, not the exact numeric pattern.

## Savoy Example

Savoy (`000002`) currently looks like this:

- `000002.R1`
- `sfp-sfpplus2` = Building 1 / MDF / `000002.OLT01`
- `sfp-sfpplus3` = roof / CNWave bridge carrying buildings behind:
  - `000002.OLT02`
  - `000002.OLT03`
  - `000002.OLT04`
  - `000002.OLT05`
  - `000002.OLT06`
  - `000002.OLT07`

### Savoy Numbering Example

- `000002.OLT01` `ONT 4` -> VLAN `1004`
- `000002.OLT01` `ONT 16` -> VLAN `1016`
- `000002.OLT03` `ONT 2` -> VLAN `3002`
- `000002.OLT05` `ONT 4` -> VLAN `5004`
- `000002.OLT07` `ONT 13` -> VLAN `7013`

This lets operations infer the subscriber attachment point directly from the VLAN ID.

## Savoy Pilot Example

This is the exact no-site-outage pilot shape discussed for Savoy.

Pilot target used for testing workflow:

- OLT: `000002.OLT03`
- OLT IP: `192.168.55.99`
- PON: `Gpon1/0/2`
- ONU: `2`
- Serial: `TPLG-D0922479`
- Assigned test VLAN: `3002`

Why this was chosen:

- `000002.OLT03` is the lightest-loaded Savoy OLT
- `Gpon1/0/2` had `0` online ONUs at the time of inspection
- this makes it suitable for syntax and workflow validation without affecting live customers

Important limitation:

- this specific ONU was offline
- it is suitable for validating config mechanics
- it does not prove end-to-end customer traffic until a live cooperative ONU/customer is migrated

### OLT Command Path Verified

The TP-Link OLT command tree was verified live to support:

```text
service-port auto config gpon 1/0/2 ont 2 gem 1 svlan 3002
```

After `svlan 3002`, the CLI accepts optional parameters including:

```text
user-vlan
user-pri
ethertype
tag-action
inner-vlan
inner-pri
traffic-in
traffic-out
desc
adminstatus
statistic-performance
<cr>
```

For a basic test, the minimal path is the direct `svlan` mapping with `<cr>`.

### MikroTik Pilot Objects

Use a dedicated test VLAN and subnet for the pilot customer.

Savoy test example:

- parent transport side: remote-building side of Savoy
- test VLAN: `3002`
- test interface name: `cust-b3-ont2`
- test subnet: `10.30.2.0/30`
- router IP: `10.30.2.1/30`
- DHCP client IP: `10.30.2.2`

Example MikroTik config:

```routeros
/interface vlan
add interface=<REMOTE_TRANSPORT_PARENT> name=cust-b3-ont2 vlan-id=3002

/ip address
add address=10.30.2.1/30 interface=cust-b3-ont2

/ip pool
add name=pool-cust-b3-ont2 ranges=10.30.2.2-10.30.2.2

/ip dhcp-server
add name=dhcp-cust-b3-ont2 interface=cust-b3-ont2 address-pool=pool-cust-b3-ont2 lease-time=30m

/ip dhcp-server network
add address=10.30.2.0/30 gateway=10.30.2.1 dns-server=8.8.8.8

/ip firewall nat
add chain=srcnat action=masquerade src-address=10.30.2.0/30 out-interface=BR-WAN comment="pilot cust-b3-ont2"

/ip firewall filter
add chain=forward src-address=10.30.2.0/30 out-interface=BR-WAN comment="pilot cust-b3-ont2 outbound"
add chain=forward dst-address=10.30.2.0/30 in-interface=BR-WAN comment="pilot cust-b3-ont2 return"
```

`<REMOTE_TRANSPORT_PARENT>` must be the correct logical parent for the remote-building trunk design at that site.
Do not guess. Validate the parent interface before deployment.

### OLT Pilot Steps

Run unsaved first.

```text
telnet 192.168.55.99
enable
configure
service-port auto config gpon 1/0/2 ont 2 gem 1 svlan 3002
exit
exit
```

Then verify:

```text
show service-port gpon 1/0/2
show mac address-table
```

### MikroTik Pilot Steps

Add the new VLAN interface and DHCP scope live, but do not remove the legacy flat service.

```routeros
/interface vlan
add interface=<REMOTE_TRANSPORT_PARENT> name=cust-b3-ont2 vlan-id=3002

/ip address
add address=10.30.2.1/30 interface=cust-b3-ont2

/ip pool
add name=pool-cust-b3-ont2 ranges=10.30.2.2-10.30.2.2

/ip dhcp-server
add name=dhcp-cust-b3-ont2 interface=cust-b3-ont2 address-pool=pool-cust-b3-ont2 lease-time=30m

/ip dhcp-server network
add address=10.30.2.0/30 gateway=10.30.2.1 dns-server=8.8.8.8

/ip firewall nat
add chain=srcnat action=masquerade src-address=10.30.2.0/30 out-interface=BR-WAN comment="pilot cust-b3-ont2"
```

### Validation Steps

For a live customer migration, validate all of the following before saving:

- customer CPE gets the new DHCP lease from the dedicated VLAN
- customer has internet access
- customer no longer appears in the legacy flat access subnet
- no private LAN leak from that customer appears in the shared bridge domain
- no rogue DHCP replies from that customer segment appear on the legacy customer bridge

### Rollback

Remove the pilot without touching the rest of the site.

OLT rollback:

```text
telnet 192.168.55.99
enable
configure
no service-port auto config gpon 1/0/2 ont 2 gem 1 svlan 3002
exit
exit
```

MikroTik rollback:

```routeros
/ip firewall nat remove [find comment="pilot cust-b3-ont2"]
/ip dhcp-server network remove [find address="10.30.2.0/30"]
/ip dhcp-server remove [find name="dhcp-cust-b3-ont2"]
/ip pool remove [find name="pool-cust-b3-ont2"]
/ip address remove [find interface="cust-b3-ont2"]
/interface vlan remove [find name="cust-b3-ont2"]
```

### Save Only After Validation

If the live pilot works and is confirmed stable:

OLT:

```text
copy running-config startup-config
```

MikroTik:

```routeros
/system backup save name=pre_customer_vlan_rollout
```

## Recommended Rollout Model

Do not try to convert the entire site by enabling `vlan-filtering` on the live flat bridge first.

Instead, use an overlay migration:

1. Leave the legacy flat customer service running.
2. Add the new per-customer VLAN service alongside it.
3. Move customers one by one.
4. Remove the flat bridge service only after migration is complete.

This is the lowest-risk path.

## OLT Design

The TP-Link OLT must map each ONU service to a dedicated VLAN using service-port configuration.

The verified command tree on Savoy OLTs shows this shape:

```text
service-port auto config gpon 1/0/X ont <ONT_ID> gem <GEM_ID> svlan <VLAN_ID> ...
```

This means the OLT can build per-ONU VLAN mappings.

### OLT Requirements

- determine the customer ONU:
  - OLT
  - PON
  - ONU ID
  - serial
- assign the customer VLAN
- create or update the service-port mapping for that ONU
- preserve ONU isolation settings:
  - `port-isolate`
  - `onu-isolate`

### OLT Operating Rules

- do not mix ad hoc flat untagged service and dedicated tagged service on the same subscriber long term
- document each ONU to VLAN assignment
- save config only after validation

## MikroTik Design

### What To Avoid

Do not keep doing this for customer access:

- one bridge
- one DHCP server
- one shared Layer 2 domain for all buildings and all customers

Do not enable `vlan-filtering=yes` on the current flat customer bridge until the full VLAN design is staged and validated.

### Preferred End State

Each customer VLAN is a routed interface on the MikroTik.

Per customer:

- VLAN interface
- IP
- DHCP pool
- DHCP server
- DHCP network
- NAT or routed policy

Example:

```routeros
/interface vlan
add interface=<PARENT_TRUNK> name=cust-b5-ont4 vlan-id=5004

/ip address
add address=10.55.4.1/30 interface=cust-b5-ont4

/ip pool
add name=pool-cust-b5-ont4 ranges=10.55.4.2-10.55.4.2

/ip dhcp-server
add name=dhcp-cust-b5-ont4 interface=cust-b5-ont4 address-pool=pool-cust-b5-ont4 lease-time=30m

/ip dhcp-server network
add address=10.55.4.0/30 gateway=10.55.4.1 dns-server=8.8.8.8

/ip firewall nat
add chain=srcnat action=masquerade src-address=10.55.4.0/30 out-interface=BR-WAN comment="cust-b5-ont4"
```

If the service model requires a larger LAN, use `/29` or `/24` as appropriate, but keep it dedicated to that customer VLAN.

## Parent Interface Strategy

The parent interface for each customer VLAN should match the transport path:

- customers on Building 1 / MDF side: terminate on the MDF-side trunk
- customers behind the CNWave mesh: terminate on the CNWave-side trunk

Do not keep those transport links as one shared flat customer bridge forever.

The long-term design should turn those uplinks into trunks, not subscriber bridges.

## Management Network

Create a separate management VLAN/subnet for:

- OLT management IPs
- transport radios
- infrastructure devices

Do not keep management IPs mixed in customer access DHCP space.

## Rollout Steps

### Phase 1: Inventory

For each site, build a table with:

- site ID
- building / OLT ID
- PON
- ONU ID
- serial
- current customer MAC
- current customer IP
- assigned customer VLAN
- migration status

### Phase 2: Trunk Validation

Validate that the transport path passes 802.1Q tags end to end:

- MDF side
- roof/backhaul side
- OLT uplink side

Do this before migrating subscribers.

### Phase 3: Pilot Customer

Pick one cooperative subscriber.

Steps:

1. create the MikroTik VLAN interface and DHCP scope
2. create/update the OLT service-port mapping for that ONU
3. move that one ONU to the new VLAN
4. verify the customer gets service
5. verify no shared L2 leakage remains for that customer
6. leave unsaved until confirmed
7. save only after validation

### Phase 4: Batch Migration

Migrate customers in small batches per building.

Suggested batch order:

1. problem customers first
2. new installs next
3. remaining customers building by building

### Phase 5: Retire Flat Service

Only after most customers are moved:

- remove the old flat customer DHCP service
- remove the old shared customer bridge model
- leave only management and explicit transport design

## Verification Checklist

For each migrated customer:

- correct ONU/VLAN mapping present on OLT
- customer receives DHCP from the dedicated VLAN
- customer has internet access
- no `192.168.88.x`, `192.168.0.x`, or other private LAN leakage visible in shared access space
- no rogue DHCP replies seen from the customer segment
- no unexpected bridge-host learning on legacy flat interfaces

## Rollback

Per customer rollback should be simple:

1. restore old OLT service mapping
2. remove or disable the customer VLAN interface on MikroTik
3. remove or disable the dedicated DHCP scope
4. verify customer is back on the legacy path

Do not save the migration until validation is complete.

## Operational Rules

- all new installs should be provisioned directly into dedicated customer VLANs
- no new customer should be added to the legacy flat bridge
- every customer VLAN must be documented
- every OLT service-port assignment must match IPAM/provisioning records
- infrastructure management must remain separate from customer service

## Minimum Standard For Other Sites

At every site:

1. verify whether customer access is currently a flat bridge
2. verify whether OLT isolation is already enabled
3. verify whether transport preserves VLAN tags
4. define the VLAN numbering plan
5. stage per-customer VLAN service on MikroTik
6. migrate one pilot customer
7. then migrate in batches

## Final Recommendation

The fastest sustainable fix is not better filtering on a flat customer bridge.

The sustainable fix is:

- per-customer VLAN at the OLT
- tagged transport across the backhaul
- routed termination on the MikroTik
- separate management plane

Savoy is the reference example of why this is necessary and how to number and roll it out cleanly.
