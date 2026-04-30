# Savoy Midnight Safe-Mode Runbook

This runbook is for the Savoy (`000002`) customer VLAN pilot scheduled for **April 3, 2026 at 12:00 AM EDT**.

This is a safe-mode runbook:

- one customer only
- no site-wide bridge conversion
- no `vlan-filtering=yes` on `BR-CGNAT`
- no save until validation
- immediate rollback if the pilot does not work cleanly

## Objective

Validate that Savoy can support a dedicated customer VLAN without taking down the site.

The pilot will answer:

1. does the CNWave/transport path pass tagged traffic end to end
2. can one customer be moved to a dedicated VLAN without impacting the rest of the site
3. can the change be rolled back immediately if needed

## Current Savoy Reality

- `000002.R1`
- `sfp-sfpplus2` = MDF / `000002.OLT01`
- `sfp-sfpplus3` = roof / CNWave mesh / `000002.OLT02-07`
- customer service today is a flat bridge:
  - `BR-CGNAT`
  - `192.168.55.0/24`
  - DHCP server `CGNAT`
- OLT isolation is already enabled
- customer leakage still occurs because aggregation is flat

## Safety Rules

- do not enable `vlan-filtering=yes` on `BR-CGNAT`
- do not touch more than one customer
- do not save OLT or MikroTik before validation
- if the customer does not come up quickly, roll back
- if the tagged preflight test fails, stop before any customer change

## Best Pilot Choice

Use the MDF side first, not the CNWave side.

Reason:

- `sfp-sfpplus2` only affects `000002.OLT01`
- `sfp-sfpplus3` affects the CNWave path for `000002.OLT02-07`
- if the transport behavior is wrong on the mesh side, the blast radius is larger

Recommended live pilot:

- one cooperative customer on `000002.OLT01`
- one unique VLAN
- one temporary DHCP scope

## Time Plan

- **11:30 PM EDT**: identify final pilot customer and confirm communication path
- **11:40 PM EDT**: gather current customer state and prep rollback notes
- **11:50 PM EDT**: stage test objects on MikroTik only
- **11:55 PM EDT**: run tagged transport preflight
- **12:00 AM EDT**: only if preflight passes, apply OLT pilot change
- **12:00 AM to 12:08 AM EDT**: validate customer service
- **12:08 AM EDT**: if not good, roll back immediately
- **12:20 AM EDT**: if stable, decide whether to save

## Required Inputs Before Start

Fill these in before the window:

- customer name or unit: `________________`
- customer OLT: `________________`
- customer PON: `________________`
- customer ONU ID: `________________`
- customer ONU serial: `________________`
- current customer MAC: `________________`
- current customer DHCP IP: `________________`
- assigned pilot VLAN: `________________`
- assigned pilot subnet: `________________`
- MikroTik parent interface: `________________`

## Preflight Validation

### 1. Confirm Current Customer State

Record:

- current DHCP lease
- current OLT location
- current MAC sightings on the router
- whether the customer is currently online and stable

### 2. Confirm Transport Parent

Do not guess the MikroTik parent interface.

For MDF-side pilot:

- expected parent is the MDF-side transport path associated with `000002.OLT01`

For CNWave-side pilot:

- expected parent is the CNWave-side transport path

If parent cannot be identified confidently: `NO-GO`

### 3. Tagged Transport Preflight

Before moving a customer, prove the path can carry a tagged VLAN.

Safe goal:

- create a temporary test VLAN interface on the MikroTik
- observe whether the OLT-side path can see the VLAN-backed service when staged
- if there is any sign tags are not passing correctly, stop

If tagged transport is not proven: `NO-GO`

## MikroTik Staging

Stage these runtime-only objects first.

Example for pilot VLAN `1004`:

```routeros
/interface vlan
add interface=<PARENT_INTERFACE> name=cust-pilot-1004 vlan-id=1004

/ip address
add address=10.10.4.1/30 interface=cust-pilot-1004

/ip pool
add name=pool-cust-pilot-1004 ranges=10.10.4.2-10.10.4.2

/ip dhcp-server
add name=dhcp-cust-pilot-1004 interface=cust-pilot-1004 address-pool=pool-cust-pilot-1004 lease-time=30m

/ip dhcp-server network
add address=10.10.4.0/30 gateway=10.10.4.1 dns-server=8.8.8.8

/ip firewall nat
add chain=srcnat action=masquerade src-address=10.10.4.0/30 out-interface=BR-WAN comment="pilot-1004"

/ip firewall filter
add chain=forward src-address=10.10.4.0/30 out-interface=BR-WAN comment="pilot-1004 outbound"
add chain=forward dst-address=10.10.4.0/30 in-interface=BR-WAN comment="pilot-1004 return"
```

Do not remove any legacy service objects during staging.

## OLT Pilot Change

Use the OLT service-port mapping for exactly one ONU.

Command shape verified on Savoy OLTs:

```text
service-port auto config gpon 1/0/X ont <ONU_ID> gem 1 svlan <VLAN_ID>
```

Example:

```text
telnet <OLT_IP>
enable
configure
service-port auto config gpon 1/0/2 ont 4 gem 1 svlan 1004
exit
exit
```

Do not save yet.

## Validation Window

Immediately after the OLT pilot change, check:

1. customer receives a DHCP lease from the pilot subnet
2. customer has internet access
3. customer is no longer using the legacy flat customer subnet
4. other Savoy customers remain stable
5. no new rogue DHCP or private LAN leakage appears from the pilot customer

## Go/No-Go Criteria

Proceed only if all are true:

- tagged transport preflight passed
- customer identity and OLT location are confirmed
- rollback commands are ready
- support contact is available

Immediate rollback if any are true:

- no DHCP lease on pilot subnet within a few minutes
- customer cannot pass traffic
- unexpected impact to other customers
- wrong parent interface suspected
- transport tagging appears not to work

## Rollback

### OLT Rollback

Use the matching service-port removal or old service restoration.

Example:

```text
telnet <OLT_IP>
enable
configure
no service-port auto config gpon 1/0/2 ont 4 gem 1 svlan 1004
exit
exit
```

If the OLT requires restoring a prior flat/default mapping, do that before leaving the session.

### MikroTik Rollback

```routeros
/ip firewall filter remove [find comment="pilot-1004 outbound"]
/ip firewall filter remove [find comment="pilot-1004 return"]
/ip firewall nat remove [find comment="pilot-1004"]
/ip dhcp-server network remove [find address="10.10.4.0/30"]
/ip dhcp-server remove [find name="dhcp-cust-pilot-1004"]
/ip pool remove [find name="pool-cust-pilot-1004"]
/ip address remove [find interface="cust-pilot-1004"]
/interface vlan remove [find name="cust-pilot-1004"]
```

Then confirm the customer is back on the legacy service.

## Save Decision

Only save if:

- the customer is stable on the pilot VLAN
- no other customers were impacted
- you are satisfied with the overnight observation risk

If saving:

OLT:

```text
copy running-config startup-config
```

MikroTik:

```routeros
/system backup save name=savoy_pre_vlan_pilot
```

## Recommended Tonight

### Safest Option

Do not move a live customer unless the tagged transport preflight is proven first.

### Preferred Live Pilot

- one cooperative customer on `000002.OLT01`
- MDF side only
- one dedicated VLAN

### Do Not Use Tonight As First Live Pilot

- CNWave-side multi-building path behind `sfp-sfpplus3`
- any change requiring `vlan-filtering=yes` on `BR-CGNAT`
- any multi-customer move

## Final Call

This runbook is intentionally conservative.

If any part of the path is uncertain at midnight:

- stop
- do not improvise
- keep the site on legacy service
- resume only after the missing proof is collected
