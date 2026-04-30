# RouterOS 7 Formulas & Patterns

This document captures the exact RouterOS 7 command patterns and logic formulas we used to derive troubleshooting conclusions from read-only data.

## 1) Core Read-Only Data Pulls

### Identity / System
```routeros
/system identity print
/system resource print
```

### Interfaces / Counters
```routeros
/interface print detail
/interface/monitor-traffic etherX once
```

### Topology (neighbors)
```routeros
/ip neighbor print detail
```

### Bridge L2 State
```routeros
/interface bridge port print detail
/interface bridge vlan print detail
/interface bridge host print detail
```

### PPP/ARP on headend router
```routeros
/ppp active print detail
/ip arp print detail
```

### Live L2 Probe Tools
```routeros
/tool mac-scan interface=etherX duration=3s
/tool sniffer set filter-interface=etherX filter-direction=any
/tool sniffer quick duration=3s
```

## 2) API Path Equivalents (RouterOS -> API)

Used through `librouteros`:

- `/system/identity`
- `/system/resource`
- `/interface`
- `/ip/neighbor`
- `/interface/bridge/port`
- `/interface/bridge/vlan`
- `/interface/bridge/host`
- `/ppp/active`
- `/ip/arp`
- `/tool/mac-scan`
- `/tool/sniffer/set`
- `/tool/sniffer/quick`
- `/tool/sniffer/stop`

## 3) One-Way Traffic Outlier Formula

We computed deltas between current scan and previous scan per running ethernet interface:

- `rx_delta = max(0, rx_now - rx_prev)`
- `tx_delta = max(0, tx_now - tx_prev)`

Thresholds:
- `low = 64 KiB`
- `mid = 256 KiB`

Classification:
- If `rx_delta == 0 && tx_delta >= low` => `tx_only`
- If `tx_delta == 0 && rx_delta >= low` => `rx_only`
- Severity:
  - `high` if active direction delta `>= mid`
  - else `medium`

## 4) Probable CPE On Port Formula

From bridge host learning on selected switch+port:

- Probable CPE if:
  - `external == true`
  - `local == false`

Used as:
- `is_probable_cpe = external && !local`

## 5) Vendor Grouping Formula (OUI)

- `vilo` if MAC starts with: `E8:DA:00`
- `tplink` if MAC starts with:
  - `30:68:93`
  - `60:83:E7`
  - `7C:F1:7E`
  - `D8:44:89`
  - `DC:62:79`
  - `E4:FA:C4`
- else: `unknown`

## 6) CPE Behavior Classification Formula (Live Sniffer)

Given packet sample + protocol counts for a MAC:

1. `pppoe`
- If any protocol key starts with `pppoe`

2. `dhcp_discovering`
- If sample has source address ending `:68 (bootpc)`
- and destination address `255.255.255.255:67 (bootps)` pattern appears

3. `igmp_linklocal_ap_like`
- If protocol includes `ip:igmp`
- and source address starts with `169.254.`

4. `silent`
- If packet count is `0` in window

5. `other`
- Any non-zero traffic not matching above

## 7) MAC Path Chain Heuristic

To build likely chain for MAC across switches:

Start switch selection (if user did not force one):
- Prefer rows where `on-interface` looks edge-like:
  - `ether*` and `external == false`
- Penalize `local == true`
- Penalize uplink-like interfaces (`sfp*`, `roof*`)

Next-hop selection:
- Prefer neighbor entry whose interface string matches the selected MAC row interface
- Else fallback to uplink-like neighbor interfaces (`sfp*`, `roof*`, `wlan*`)

Hop health overlay:
- If interface at hop is present in outlier table with `tx_only` or `rx_only`, mark hop degraded

## 8) Building/Uplink Scoring Heuristic (Map)

For each CRS switch, candidate uplink edges are scored:

- `+300` if target is non-CRS (core/router)
- `+120` if target is CRS
- `+160` if interface starts `sfp`
- `+120` if interface includes `ether24` or ends `24`
- `+90` if interface includes `uplink` or `trunk`
- `-60` if interface starts `bridge`
- `+20` if interface starts `ether1`

Best-scored candidate selected as logical uplink.

## 9) Directionality Interpretation Rule

For a customer-facing access port expected 1:1 CPE:

- If sniffer/mac-scan sees many MACs but bridge host local view only shows switch/local MAC:
  - treat as L2 flood visibility, not true physical behind-port fanout

- If live sniffer on port shows mostly one direction only (`->` or `<-`) for long windows:
  - suspect upstream return-path, VLAN policy mismatch, or profile mismatch on CPE mode

## 10) 30-Minute Watch Construction Pattern

Long watch is composed from repeated short probes:

- For each target `(switch_ip, interface, mac)`:
  - run `/tool sniffer quick duration=1s` with `filter-interface` + optional `filter-mac-address`
- Repeat across targets for full duration
- Aggregate:
  - `total_packets`
  - `protocol_counts`
  - class counts (`pppoe`, `dhcp_discovering`, `igmp_linklocal_ap_like`, `silent`, `other`)
- Determine dominant class per target

## 11) Safety Constraint Used Throughout

All formulas above assume read-only operations unless explicitly doing manual remediation.

Read-only set includes:
- `print`
- `monitor`
- `mac-scan`
- `sniffer quick`

No config mutation needed for the analytics/classification outputs.

## 12) Handy RouterOS 7 Script Functions / Snippets

These are small reusable scriptlets for field troubleshooting.

### A) OUI Alt-MAC Pair Finder (`30:*` vs `32:*`)

Use when you suspect devices may present alternate local-admin MAC variants.

```routeros
:foreach i in=[/interface/bridge/host/find where mac-address~"^30:68:93"] do={
    :local mac [/interface/bridge/host/get $i mac-address]
    :local tail [:pick $mac 2 [:len $mac]]
    :local altMac ("32" . $tail)

    :if ([:len [/interface/bridge/host/find where mac-address=$altMac]] > 0) do={
        :put ("PAIR FOUND " . $mac . " <-> " . $altMac)
    }
}
```

### B) Generic OUI Host Lister (bridge host table)

```routeros
:local re "^E8:DA:00"
:foreach i in=[/interface/bridge/host/find where mac-address~$re] do={
    :put (\
      [/interface/bridge/host/get $i mac-address] . "  " . \
      [/interface/bridge/host/get $i on-interface] . "  vid=" . \
      [/interface/bridge/host/get $i vid] . "  local=" . \
      [/interface/bridge/host/get $i local] . "  external=" . \
      [/interface/bridge/host/get $i external] \
    )
}
```

### C) CPE Candidate Filter (external + non-local)

```routeros
:foreach i in=[/interface/bridge/host/find where external=yes && local=no] do={
    :put (\
      [/interface/bridge/host/get $i mac-address] . "  " . \
      [/interface/bridge/host/get $i on-interface] . "  vid=" . \
      [/interface/bridge/host/get $i vid] \
    )
}
```

### D) Per-Port MAC Cardinality Check (1:1 policy sanity)

Prints per-port MAC count so you can spot ports seeing many hosts.

```routeros
:foreach p in=[/interface/find where type="ether"] do={
    :local n [/interface/get $p name]
    :local c [:len [/interface/bridge/host/find where on-interface=$n]]
    :if ($c > 1 && $n != "ether24") do={
        :put ("OUT-OF-POLICY " . $n . " hosts=" . $c)
    }
}
```

### E) Quick PPPoE Discovery Presence Check On Interface

```routeros
/tool/sniffer/set filter-interface=ether39 filter-direction=any filter-mac-protocol=pppoe-discovery
:local n 0
:foreach i in=[/tool/sniffer/quick duration=5s] do={ :set n ($n + 1) }
:put ("PPPOE-DISCOVERY-PKTS=" . $n)
/tool/sniffer/stop
```

### F) Quick DHCP Discover Presence Check On Interface

```routeros
/tool/sniffer/set filter-interface=ether39 filter-direction=any filter-mac-protocol=ip
:local dhcp 0
:foreach r in=[/tool/sniffer/quick duration=5s] do={
    :local s ($r->"src-address")
    :local d ($r->"dst-address")
    :if ([:typeof $s]!="nil" && [:typeof $d]!="nil") do={
        :if (($s~"0.0.0.0:68") && ($d~"255.255.255.255:67")) do={ :set dhcp ($dhcp + 1) }
    }
}
:put ("DHCP-DISCOVER-PKTS=" . $dhcp)
/tool/sniffer/stop
```

### G) IGMP Link-Local AP-Like Signal Check

```routeros
/tool/sniffer/set filter-interface=ether39 filter-direction=any filter-mac-protocol=ip
:local igmpLL 0
:foreach r in=[/tool/sniffer/quick duration=5s] do={
    :local p ($r->"protocol")
    :local s ($r->"src-address")
    :if ([:typeof $p]!="nil" && [:typeof $s]!="nil") do={
        :if (($p="ip:igmp") && ($s~"^169.254.")) do={ :set igmpLL ($igmpLL + 1) }
    }
}
:put ("IGMP-LINKLOCAL-PKTS=" . $igmpLL)
/tool/sniffer/stop
```

### H) Build Local OUI Count Summary

```routeros
:local vilo 0
:local tplk 0
:local unk 0

:foreach i in=[/interface/bridge/host/find] do={
    :local m [/interface/bridge/host/get $i mac-address]
    :if ($m~"^E8:DA:00") do={
        :set vilo ($vilo + 1)
    } else={
        :if (($m~"^30:68:93") || ($m~"^60:83:E7") || ($m~"^7C:F1:7E") || ($m~"^D8:44:89") || ($m~"^DC:62:79") || ($m~"^E4:FA:C4")) do={
            :set tplk ($tplk + 1)
        } else={
            :set unk ($unk + 1)
        }
    }
}

:put ("VILO=" . $vilo . " TPLINK=" . $tplk . " UNKNOWN=" . $unk)
```

### I) Neighbor/Uplink Quick Print (CRS focus)

```routeros
:foreach i in=[/ip/neighbor/find] do={
    :local ifn [/ip/neighbor/get $i interface]
    :if (($ifn~"^sfp") || ($ifn~"roof") || ($ifn~"wlan")) do={
        :put ($ifn . " -> " . [/ip/neighbor/get $i identity] . " (" . [/ip/neighbor/get $i address] . ")")
    }
}
```

### J) Port Directionality Snapshot (rx/tx one-shot)

```routeros
:local ifn "ether39"
:local m [/interface/monitor-traffic $ifn once as-value]
:put ($ifn . " rx-bps=" . ($m->"rx-bits-per-second") . " tx-bps=" . ($m->"tx-bits-per-second"))
```
