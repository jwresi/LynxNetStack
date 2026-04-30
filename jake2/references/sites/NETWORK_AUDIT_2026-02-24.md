# 192.168.44.0/24 Read-Only Network Audit Baseline

Date: 2026-02-24
Source of truth used:
- Live crawl attempt on 2026-02-24 (scan_id=9): no API reachability from current host at time of run.
- Last complete crawl (scan_id=8, 2026-02-16): used for baseline mapping below.

## Coverage
- Devices discovered (scan_id=8): 62
- CRS switches: 61
- Router/core: 1 (`000007.R1`, `192.168.44.1`)

## Firmware Versioning
Version spread across 62 devices:
- 7.18.2 (stable): 39
- 7.20.6 (stable): 10
- 7.16.2 (stable): 3
- 7.15.2 (stable): 2
- 7.14.3 (stable): 6
- 7.14.2 (stable): 2

Risk note:
- Significant mixed-version environment (7.14.x through 7.20.6) across same L2 domain.

## VLAN Handling / Separation
Observed VLAN IDs in bridge VLAN tables:
- `1`: 61 devices
- `10`: 62 devices
- `20`: 61 devices
- `30`: 61 devices
- `10,20,30`: 1 device

Notable VLAN table anomalies:
- `000007.031.SW02` (`192.168.44.111`): only 1 VLAN row (`10`) captured.
- `000007.051.SW01` (`192.168.44.113`): 3 rows (`10|20|30`), missing VLAN 1 row.
- `000007.036.SW03` (`192.168.44.115`): duplicate/extra rows (`20|10|30|1|10,20,30`).
- `000007.053.RFSW01` (`192.168.44.16`): duplicate VLAN 1 rows (`10|20|30|1|1`).

Risk note:
- Inconsistent bridge VLAN table shape across devices suggests config drift.

## Port Roles vs Forwarding Behavior
Bridge-port policy distribution (1832 rows):
- `ingress-filtering=1`: 1829
- `ingress-filtering=0`: 3 (all on `000007.004.RFSW01`)
- `trusted=1`: 2 ports (`000007.058.RFSW01 Eth1`, `000007.004.RFSW01 ether1`)

Frame types distribution:
- `admit-all`: 1664
- `admit-only-vlan-tagged`: 143
- `admit-only-untagged-and-priority-tagged`: 25

PVID distribution:
- `20`: 1477
- `1`: 271
- `30`: 54
- `10`: 30

Risk note:
- Access-facing ports are overwhelmingly `admit-all` with PVID 20, which is permissive for a noisy flat L2 if strict edge behavior is desired.

## Customer Isolation Signals
Expected policy context (from your guidance): most customer edge ports should be 1:1 CPE.

In scan_id=8, many non-uplink Ethernet ports show multiple MACs on VLAN 20.
Examples (excluding ether24):
- `000007.042.SW01 ether12`: 5 MACs
- `000007.002.SW02 ether6`: 5 MACs
- `00007.055.SW05 ether27`: 4 MACs
- Many additional ports with 2-3 MACs

Risk note:
- Either unmanaged fan-out devices/meshing exist behind customer ports, or L2 leakage/bridging is violating intended one-CPE-per-port behavior.

## Loop Prevention / L2 Stability Signals
One-way forwarding outliers (delta-based, scan 7 -> 8):
- Outlier rows: 62
- Affected switches: 19
- Heaviest devices:
  - `000007.052.SW01`: 10 ports tx-only
  - `000007.063.SW01`: 9 ports tx-only
  - `000007.025.SW01`: 7 ports tx-only
  - `000007.031.SW01`: 5 ports tx-only

Example severe counters:
- `000007.062.SW01 ether5`: `rx_byte=0`, `tx_byte=42697821255`

Risk note:
- Persistent tx-only edges indicate frequent unidirectional behavior (physical/media, policy, or upstream forwarding asymmetry), not isolated incidents.

## MTU / Frame Size Consistency + Jumbo Readiness
Observed `mtu/actual-mtu` on `type=ether` interfaces:
- `1500/1500`: 1862 interfaces
- `1592/1592`: 1 interface (`000007.004.RFSW01 sfp-sfpplus4`)

Risk note:
- Baseline is mostly consistent at 1500, but at least one non-standard port exists.
- Before jumbo migration, full L2 path verification must include: bridge, access/uplink ports, VLAN interfaces, radio links, and inter-switch trunks.

## Multicast / Broadcast Behavior
Direct packet-type counters are not stored in current mapper schema.
Indirect signals indicating loud L2 flooding behavior:
- Very high MAC learning counts on uplink/trunk ports (hundreds per uplink).
- Widespread tx-only outlier pattern across many switches.

Recommendation for next read-only iteration:
- Add per-interface capture counters for broadcast/multicast/unknown-unicast on representative core/distribution edges.

## Topology Baseline (Likely Structure)
- Core router: `000007.R1` (`192.168.44.1`)
- Multi-switch distribution chains present (examples):
  - `000007.001.SW02 -> 000007.001.SW01`
  - `000007.061.SW02 -> 000007.061.SW01`
  - `000007.060.SW02 -> 000007.060.SW01`
  - `000007.032.SW02 -> 000007.032.SW01`
  - `000007.038.SW02 -> 000007.038.SW01`
- Several nodes show multiple discovered neighbors on one uplink-facing interface, consistent with a very loud/flat L2 neighborhood view.

## Important Limitation
- Live scan from current host at 2026-02-24 could not reach API on subnet (`scan_id=9 api_reachable=0`).
- This baseline is accurate to the last full crawl (`2026-02-16`) and should be refreshed once management-path reachability is restored.
