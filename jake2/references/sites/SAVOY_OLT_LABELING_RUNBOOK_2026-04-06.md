# Savoy (000002) — OLT ONT Labeling Runbook
Generated: 2026-04-06 via Jake MAC table correlation

## Method
1. Pulled live bridge hosts from 000002.R1 (172.27.62.127)
2. Cross-referenced CPE MACs against TP-Link local export (network names)
3. Looked up each MAC via `show mac address-table address <mac>` across all 7 OLTs
4. Generated description commands for all matched ONTs

## Results
- 20 ONTs successfully mapped to unit names
- 18 ONTs not mappable (MAC aged out of OLT forwarding table — re-run after traffic)
- OLT02 and OLT06: no mappings found (may serve buildings not yet active)

## Commands — Run On Each OLT

### 000002.OLT01 (192.168.55.98)
configure
interface gpon 1/0/1
ont description 1 description Savoy1Unit2N
ont description 4 description Savoy1Unit5H
ont description 6 description Savoy1Unit10G
ont description 7 description Savoy1Unit9K
ont description 12 description Savoy1Unit1S
exit
interface gpon 1/0/2
ont description 1 description Savoy1Unit16K
ont description 2 description Savoy1Unit3N
ont description 5 description Savoy1Unit11R
ont description 6 description Savoy1Unit17C
ont description 16 description Savoy7Unit8C
exit
end
copy running-config startup-config

### 000002.OLT03 (192.168.55.99)
configure
interface gpon 1/0/1
ont description 2 description Savoy3Unit7D
exit
end
copy running-config startup-config

### 000002.OLT04 (192.168.55.96)
configure
interface gpon 1/0/1
ont description 2 description Savoy4Unit10F
ont description 3 description Savoy4Unit11N
ont description 5 description Savoy4Unit16C
exit
interface gpon 1/0/2
ont description 8 description Savoy4Unit6N
exit
end
copy running-config startup-config

### 000002.OLT05 (192.168.55.95)
configure
interface gpon 1/0/1
ont description 2 description Savoy5Unit6H
ont description 11 description Savoy5Unit4S
exit
end
copy running-config startup-config

### 000002.OLT07 (192.168.55.93)
configure
interface gpon 1/0/1
ont description 2 description Savoy7Unit4H
exit
interface gpon 1/0/2
ont description 3 description Savoy7Unit15J
ont description 4 description Savoy7Unit10S
exit
end
copy running-config startup-config

## Not Yet Mapped (MAC aged out — retry after subscriber traffic)
Savoy1Unit2R, Savoy1Unit1M, Savoy1Unit4D, Savoy1Unit6G, Savoy1Unit9J,
Savoy1Unit11K, Savoy2Unit16R, Savoy2Unit17L, Savoy3Unit15S, Savoy4Unit3M,
Savoy4Unit12K, Savoy4Unit17G, Savoy5Unit2B, Savoy5Unit4R, Savoy5Unit8R,
Savoy5Unit17P, Savoy6Unit12G, Savoy7Unit8R, Savoy7Unit9D, Savoy7Unit12J

## To map remaining units
Wait for subscriber traffic, then re-run:
  show mac address-table address <cpe_mac>
across all OLTs. The MAC table entries age out after ~300 seconds of inactivity.

## OLT Telnet Access
  telnet <olt_ip>
  User: admin
  Password: (see .env)
  enable
