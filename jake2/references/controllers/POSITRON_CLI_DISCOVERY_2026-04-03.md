# Positron CLI Discovery 2026-04-03

Target device:
- `000004.Positron02`
- IP: `192.168.111.11`
- Site: `000004`
- Role: `G.Hn`
- Model: `GAM-4-CX-AC`

Credentials/source:
- Username found in repo envs: `admin`
- Shared password found in repo envs

Access results:
- HTTP `80/tcp`: reachable enough to return `401 Unauthorized` with `WWW-Authenticate: Basic realm="PositronGAM"` on one probe
- HTTPS `443/tcp`: not listening
- SSH `22/tcp`: reachable and usable
- Telnet `23/tcp`: refused

## SSH / CLI Findings

Login over SSH succeeded and exposed a `#` prompt.

Top-level `?` shows these major branches:
- `configure`
- `copy`
- `delete`
- `dir`
- `disable`
- `dot1x`
- `enable`
- `erps`
- `firmware`
- `ghn`
- `ip`
- `ipv6`
- `link-oam`
- `ping`
- `platform`

Notes:
- Inline help forms like `show ?` and `ghn ?` did not behave cleanly from the scripted shell even though `help` says they should.
- Direct read commands do work.

## Confirmed Working Read Commands

### `show version`
Key output:
- System: `GAM-4-CX-AC GigaBit Ethernet Switch`
- MAC: `00-0e-d8-1a-b9-e2`
- Uptime: `13d 07:19:55`
- Active image version: `GAM-4/8-C_v1.5.4`
- Code revision: `24791`
- Product: `Positron GAM-4/8-C Switch`

### `dir`
Key output:
- `default-config`
- `startup-config`
- flash size/free reported

### `show running-config`
Key findings:
- default routes:
  - `0.0.0.0/0 via 172.30.55.1`
  - `0.0.0.0/0 via 192.168.111.1`
- management VLAN:
  - `interface vlan 100`
  - `ip address 192.168.111.11 255.255.255.0`
- uplink:
  - `interface 10GigabitEthernet 1/1`
  - trunk mode
  - native VLAN `100`
  - allowed VLANs `3-4094`
- G.hn ports:
  - `interface G.hn 1/1`
  - `interface G.hn 1/2`
  - `interface G.hn 1/3`
  - `interface G.hn 1/4`
- subscriber VLAN pattern:
  - G.hn ports allow subscriber VLAN `10`
  - management/transport VLANs include `2`, `4094`, native `4095`
- explicit endpoint records found:
  - examples:
    - `ghn endpoint 1 ... port 3 description "Cambridgeunit117D"`
    - `ghn endpoint 2 ... port 3 description "Cambridgeunit116C"`
    - `ghn endpoint 3 ... port 1 description "Cambridgeunit117F"`
- explicit subscriber records found:
  - examples:
    - `ghn subscriber 1 name "Unit117D" vid 10 endpoint 1 ...`
    - `ghn subscriber 2 name "Unit116C" vid 10 endpoint 2 ...`
    - `ghn subscriber 3 name "Unit117F" vid 10 endpoint 3 ...`
    - `ghn subscriber 12 name "CambridgeUnit117B" vid 10 endpoint 12 ...`

This is important:
- the Positron config is already a customer/subscriber mapping source
- Jake can potentially use it to correlate unit names -> G.hn endpoint -> port -> building device

### `show ip route`
Output:
- `0.0.0.0/0 via 192.168.111.1`
- `192.168.111.0/24 via VLAN100`

### `show ip interface brief`
Output:
- `VLAN 1 192.168.10.11/24 DOWN`
- `VLAN 100 192.168.111.11/24 UP`

## Operational Conclusions

For Cambridge Positrons, Jake now has proof that:
- live SSH CLI access is possible
- telnet is not required for these Positrons
- the device exposes a structured, switch-like CLI
- the running config contains directly useful G.hn endpoint and subscriber mapping data

## Best Next Steps

1. Add a deterministic Positron read path to Jake
- `show version`
- `show ip interface brief`
- `show ip route`
- `show running-config`

2. Parse `show running-config` into:
- G.hn port inventory
- endpoint list
- subscriber list
- VLAN model
- uplink/native VLAN model

3. Use this for Cambridge-specific questions like:
- which units are configured on this Positron?
- which G.hn port serves Unit117D?
- is this Positron carrying subscriber VLAN 10?
- what is the uplink/native VLAN design on this box?
