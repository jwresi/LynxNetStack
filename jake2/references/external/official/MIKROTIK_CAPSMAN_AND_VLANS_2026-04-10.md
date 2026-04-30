# MikroTik CAPsMAN And VLANs

- Source URLs:
  - https://help.mikrotik.com/docs/spaces/ROS/pages/7962638/CAPsMAN
  - https://help.mikrotik.com/docs/spaces/ROS/pages/137986075/CAPsMAN%20with%20VLANs
- Source type: official documentation
- Intake date: 2026-04-10
- Use for: CAPsMAN troubleshooting, VLAN forwarding design, local-vs-manager forwarding decisions

## High-signal points for Jake

1. CAPsMAN has two major forwarding modes:
- local forwarding
- manager forwarding

2. In local forwarding mode:
- traffic is forwarded by the CAP itself
- the CAP can tag traffic before it leaves toward the network
- this is the mode that works naturally with downstream switching decisions and VLAN-limited switch ports

3. In manager forwarding mode:
- CAP traffic is encapsulated toward CAPsMAN
- a switch in the middle cannot distinguish the VLAN ID set by the CAP because the tag is inside the CAPsMAN encapsulation
- this is useful for centralized processing across L3-remote CAPs, but it changes how VLAN reasoning should be done

4. VLAN-related CAPsMAN datapath settings that matter operationally:
- `datapath.local-forwarding`
- `datapath.vlan-id`
- `datapath.vlan-mode`
- bridge membership / bridge VLAN filtering on the relevant box

5. CAPsMAN troubleshooting implication:
- if an AP joins CAPsMAN but clients do not land on the intended VLAN, Jake should treat that as datapath / VLAN admission / trunking first, not a CAP join problem

## Jake operator read

For CAPsMAN + VLAN failures, Jake should verify in this order:

1. effective CAPsMAN datapath and provisioning
2. whether the AP is doing local forwarding or manager forwarding
3. bridge VLAN table / trunk membership on the AP and upstream switch
4. SSID-to-VLAN binding
5. DHCP/gateway reachability on the intended VLAN

## Why this belongs in RAG

This is stable vendor behavior and operational doctrine, not training behavior.
