# NYCHA Vilo Recovery Candidates 2026-04-03

This ranking uses only confirmed safe evidence sources:

- latest bridge-host / trace evidence from `network_map.db`
- current Vilo audit artifacts under the old Jake `output/` tree
- confirmed Vilo beta API read surface:
  - inventory
  - networks
  - subscribers
  - vilos

## Tier 1: True Edge Recovery Candidate

- `e8:da:00:14:f8:f6`
  - sighting: `000007.001.SW01 ether6 vlan20`
  - trace status: `edge_trace_found`
  - Vilo cloud inventory: no exact match
  - interpretation:
    - this is the strongest current “real unconfigured Vilo on a customer edge port” candidate
    - unlike many other Vilo MACs, this one is uniquely meaningful at an access port and not just a cloud-stale object
    - this is the port currently being held in recovery on `VLAN 30`

## Tier 2: Active Recovery-Ready Candidate

- `e8:da:00:15:00:a5`
  - sighting: `000007.051.SW02 ether14 vlan30`
  - audit classification: `inventory_matched_attention_port`
  - port status: `recovery_ready`
  - Vilo cloud object: `Vilo_00a5`
  - interpretation:
    - this is a real known Vilo currently staged on `VLAN 30`
    - it is a valid recovery candidate, but not the same class as `f8:f6`
    - cloud knows it; the issue is recovery/adoption state, not missing cloud identity

## Tier 3: Recovery Hold Ports With Known Offline Objects

- `e8:da:00:15:03:99`
  - `000007.051.SW02 ether18 vlan30`
  - `recovery_hold`
- `e8:da:00:15:00:99`
  - `000007.051.SW02 ether19 vlan30`
  - `recovery_hold`
- `e8:da:00:15:00:b7`
  - `000007.051.SW02 ether22 vlan30`
  - `recovery_hold`

Interpretation:

- these are legitimate staged recovery ports
- but they have not yet shown the same encouraging signal as `recovery_ready`
- they should be treated as “hold and observe” rather than the first port to pivot attention toward

## Tier 4: Clean-Switch Untracked Vilo Candidates Worth Future Follow-Up

- `e8:da:00:15:06:9a`
  - `000007.060.SW01 ether4 vlan20`
  - port comment `1D`
- `e8:da:00:14:e0:4e`
  - `000007.070.SW01 ether9 vlan20`
- `e8:da:00:14:e2:c4`
  - `000007.032.SW02 ether16 vlan20`
- `e8:da:00:14:ec:7e`
  - `000007.035.SW01 ether9 vlan20`
- `e8:da:00:14:fa:6a`
  - `000007.035.SW01 ether20 vlan20`

Interpretation:

- these are worth follow-up because they are seen on clean customer access ports and are not in Vilo inventory
- they are lower-priority than `f8:f6` because they are not in the active emergency recovery path right now

## Not Good Recovery Leads

- `e8:da:00:15:09:b7`
- `e8:da:00:14:f8:f5`

Interpretation:

- these are real Vilo cloud objects
- both are offline
- both point at the same local control IP `192.168.58.1`
- neither is found directly in the latest bridge-host scan
- they look like stale duplicate cloud residues tied to the local Vilo control plane, not clean current edge-port targets

## Operational Read

Right now the best NYCHA port to keep in active recovery is:

- `000007.001.SW01 ether6`
  - target MAC family: `e8:da:00:14:f8:f6`

The best secondary staged recovery port is:

- `000007.051.SW02 ether14`
  - target MAC: `e8:da:00:15:00:a5`

Jake should rank:

1. edge-only untracked candidate on a real customer port
2. then `recovery_ready` VLAN30 ports with cloud-known objects
3. then `recovery_hold` VLAN30 ports
4. then clean-port untracked Vilo sightings
5. and last, stale duplicate cloud-only objects on `192.168.58.1`
