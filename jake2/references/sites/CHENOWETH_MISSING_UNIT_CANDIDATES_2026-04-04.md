# Chenoweth Missing Unit Candidates 2026-04-04

Site:
- `000008`
- `Chenoweth`

Grounded inputs:
- historical Chenoweth subscriber export from 2026-02-10
- historical HC220 export from 2026-04-03
- old Jake RouterOS export `tikbreak/000008.R1.rsc`

Current site-level state:
- `91` live Chenoweth HC220 rows in the latest TP-Link export
- buildings seen in live data:
  - `Chenoweth1`
  - `Chenoweth3`
  - `Chenoweth5`
  - `ChenowethB1LeasingOffice`
- public IP observed across the site export: `12.77.119.146`
- current private WANs are primarily `100.64.3.x`

## High Confidence Missing

These units were present in the February Chenoweth export but are absent from the April 3, 2026 export.

- `Chenoweth1Unit103`
  - last seen in Feb export
  - serial `Y24A0N0001343`
  - MAC `30:68:93:a7:1d:2a`
  - last recorded WAN `100.64.3.220`
  - TAUC network still exists:
    - `networkId=11784420722707`
    - `deviceId=aSBbSAg0tq00GCzWtzHxLleeh9pObnu7GIRK_xmxpJ0SmR_ZSGihM09VfpuMVyEO`
    - `preConfigEnable=true`
    - `preConfig.operationMode=Router`
    - `preConfig.internet.type=none`
- `Chenoweth1Unit201`
  - last seen in Feb export
  - serial `Y24A0N0000997`
  - MAC `30:68:93:a7:19:1c`
  - last recorded WAN `100.64.3.174`
  - TAUC network still exists:
    - `networkId=11784421116933`
    - `deviceId=GnuENM9-agNN_WA2iuBidxEk4425vIRqJ0P-fu_V4mgOaxqXid_8TE0OuuAvuFZ3`
    - `preConfigEnable=true`
    - `preConfig.operationMode=Router`
    - `preConfig.internet.type=none`
- `Chenoweth3Unit114`
  - last seen in Feb export
  - serial `Y24A0N0000384`
  - MAC `30:68:93:a7:11:ed`
  - last recorded WAN `100.64.3.109`
  - TAUC network still exists:
    - `networkId=11784421836812`
    - `deviceId=g52WRN0gkVBftpvLPMITj70ItowRgj-GdxgkpPSOStjhjoLHcBrtxpyKfES7F0gY`
    - `preConfigEnable=true`
    - `preConfig.operationMode=Router`
    - `preConfig.internet.type=none`

## Lower Confidence Gaps

These units are absent from the latest export when compared against the dominant numbering pattern of `100-116` and `200-216` within each building. They were not confirmed as online in the February export, so they should be treated as possible vacancies, unprovisioned units, or long-term inactive subscribers until corroborated.

Building 1:
- `Chenoweth1Unit109`

Building 3:
- `Chenoweth3Unit107`
- `Chenoweth3Unit208`
- `Chenoweth3Unit215`

Building 5:
- `Chenoweth5Unit101`
- `Chenoweth5Unit103`
- `Chenoweth5Unit106`
- `Chenoweth5Unit107`
- `Chenoweth5Unit113`

## Operational Guidance

- Start with the `High Confidence Missing` set.
- Do not assume the `Lower Confidence Gaps` are faults until they are confirmed against customer records or field occupancy.
- The current Chenoweth problem picture is not a site-wide outage:
  - latest export still shows `91` online HC220 customers
  - Jake currently sees `0` active alerts on `000008`
  - likely work is per-unit, not fabric-wide
- The three high-confidence missing units are not deleted cloud records:
  - `get_tauc_network_details(network_id)` still returns valid HC220 records for all three
  - `get_tauc_device_detail(device_id)` returns valid serial/MAC/model/firmware for all three
  - they are absent from the latest online export, but still present in TAUC cloud
- Live router-side check on `000008.R1` (`172.27.60.111`) now confirms:
  - `Chenoweth1Unit103`
    - no current DHCP lease by historical MAC
    - no current DHCP lease by historical WAN `100.64.3.220`
    - no ARP presence by historical MAC or historical WAN
  - `Chenoweth1Unit201`
    - no current DHCP lease by historical MAC
    - no current DHCP lease by historical WAN `100.64.3.174`
    - no ARP presence by historical MAC or historical WAN
  - `Chenoweth3Unit114`
    - no current DHCP lease by historical MAC
    - no ARP presence by historical MAC
    - historical WAN `100.64.3.109` is currently bound to a different live HC220 MAC `30:68:93:A7:16:AF`
- Alternate-MAC drift does not explain these three:
  - no nearby current Chenoweth MAC hits for the historical HC220 MACs of `1Unit103`, `1Unit201`, or `3Unit114`
- Current blockers to direct remote recovery from this host:
  - TAUC `preconfiguration_status` and `pppoe_status` are blocked by permission error `-70312`
  - NetBox has the real Chenoweth site and switches, but no per-unit CPE objects or customer-port labels for these units
  - `ssh_mcp` does not help at Chenoweth because the building switches are `SwitchOS`, not RouterOS

## Live SwitchOS Findings

Real Chenoweth access switches and direct management IPs:
- `000008.003.SW01` -> `100.64.3.232`
- `000008.005.SW01` -> `100.64.3.234`
- `000008.006.SW01` -> `100.64.3.235`

Grounded from live SwitchOS digest-auth reads:
- `000008.003.SW01`
  - `Chenoweth3Unit114`
    - port label/comment: `Cheno3Unit114`
    - current live state:
      - `port 14` enabled, link up, but learning `Chenoweth3Unit113` MAC `3C:78:95:6C:48:B8`
      - `port 15` enabled, no link, no learned host
      - `port 16` enabled, link up, learning `Chenoweth3Unit115` alternate-MAC-side host `3C:78:95:6C:4A:C5`
    - operator read:
      - `3Unit114` is not just absent from TAUC; its intended switch area is currently wrong/misaligned at the edge
      - safest field target is the dark `port 15`
- `000008.005.SW01`
  - `Chenoweth1Unit103`
    - `port 3` comment: `306893a71113 ALT`
    - current live state:
      - enabled, link up
      - learning `30:68:93:A7:11:13` and `32:68:93:A7:11:13`
    - router-side state on `000008.R1`:
      - `30:68:93:A7:11:13` has live DHCP lease `10.250.68.67`
      - that lease is in `address-lists=Reject_0`
    - operator read:
      - `1Unit103` is not dead
      - it is presenting on an alternate HC220 MAC and being dropped into the reject DHCP pool
      - this is a backend MAC-binding / authorization problem, not a dark-port problem
  - `Chenoweth1Unit201`
    - `port 24` comment: `Cheno1Unit201`
    - current live state:
      - enabled, link up
      - learning `Chenoweth1Unit205` MAC `3C:78:95:6C:45:16`
      - router-side lease for that MAC is normal live customer lease `100.64.3.93`
    - operator read:
      - this is a wrong-port / mispatch condition
      - `1Unit201` is not on its labeled port right now

Current best fix ordering:
1. `Chenoweth1Unit103`
   - treat as remotely fixable first
   - resolve why alternate MAC `30:68:93:A7:11:13` is landing in `Reject_0`
2. `Chenoweth1Unit201`
   - field wrong-port cleanup
   - labeled unit port is occupied by `1Unit205`
3. `Chenoweth3Unit114`
   - field edge cleanup on `000008.003.SW01`
   - intended switch area is misaligned and adjacent dark port `15` is the safest physical target
