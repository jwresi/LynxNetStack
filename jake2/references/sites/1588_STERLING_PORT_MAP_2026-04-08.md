# 1588 Sterling Pl — Port Map Audit
Generated: 2026-04-08 via Jake (000007.074.SW01 live read)

## Switch
- Device: 000007.074.SW01
- IP: 192.168.44.169
- Building: 000007.074

## Current Port State (Live)

| SW Port | MAC | Identified As | Status | Issue |
|---------|-----|--------------|--------|-------|
| ether1 | E8:DA:00:14:E6:35 | Vilo mesh satellite | ONLINE | Mesh node, not primary |
| ether2 | E8:DA:00:14:EC:DD | Vilo mesh satellite | ONLINE | Mesh node, not primary |
| ether3 | E8:DA:00:14:E3:BF | Vilo mesh satellite | ONLINE | Mesh node, not primary |
| ether5 | E8:DA:00:14:E3:A1 | Vilo mesh satellite | ONLINE | Mesh node, not primary |
| ether12 | 60:83:E7:AF:66:CA | TP-Link HC220-G5 | UNKNOWN | Not in any system |
| ether20 | 7 MACs | Unknown downstream | — | Sub-switch or AP |
| ether4,6-11,13-19,21-23 | — | Empty | — | 17 unused ports |

## Root Problem

The 4 Vilo nodes on ether1/2/3/5 are **satellite mesh nodes** from network
`Vilo_03b1` whose **primary router** (E8:DA:00:15:03:B1) is located elsewhere.
These satellites have been cabled into tenant ports at 1588 Sterling without
their primary, meaning they're providing internet via mesh backhaul to a
primary located at a different address.

## Vilo Networks Registered at 1588 Sterling (20 total)

| Network Name | Primary MAC | Status |
|-------------|-------------|--------|
| Vilo_03b1 | E8:DA:00:15:03:B1 | ONLINE (primary elsewhere) |
| Vilo_e431 | E8:DA:00:14:E4:31 | ONLINE |
| Vilo_07ad | E8:DA:00:15:07:AD | ONLINE |
| Vilo_fc07 | E8:DA:00:14:FC:07 | ONLINE |
| Vilo_ff55 | E8:DA:00:14:FF:55 | ONLINE |
| Vilo_0b37 | E8:DA:00:15:0B:37 | ONLINE |
| Vilo_02d9 | E8:DA:00:15:02:D9 | OFFLINE |
| Vilo_06b7 | E8:DA:00:15:06:B7 | OFFLINE |
| + 12 more offline | — | OFFLINE |

**Only 6 of 20 registered networks are ONLINE. None of the 6 ONLINE primaries
appear on this switch's bridge table** — they may be connected to a different
switch port or not connected at all.

## Action Required

1. **Locate and remove** the 4 mesh satellites (ether1/2/3/5) from `Vilo_03b1`
   network via Vilo ISP portal, then factory reset each unit
2. **Identify** which unit numbers correspond to which switch ports
   (port labeling or physical visit required — no subscriber names in any system)
3. **Re-provision** each Vilo as an independent subscriber network
4. **Investigate** why 14 of 20 registered networks are OFFLINE
5. **Identify** ether12 TP-Link (60:83:E7:AF:66:CA) — not in TAUC, Vilo, or Splynx

## Port → Unit Hypothesis (based on port order)

Without physical labeling or subscriber records, port-to-unit mapping is
estimated based on sequential port numbering:

| Port | Estimated Unit | Confidence |
|------|---------------|------------|
| ether1 | Unit 1A or 1st floor A | Low |
| ether2 | Unit 1B or 1st floor B | Low |
| ether3 | Unit 1C or 1st floor C | Low |
| ether5 | Unit 1E (unit D vacant?) | Low |
| ether12 | Unit 12 or floor 2 | Low |
| ether20 | Unit 20 / sub-switch | Low |

**These are estimates only. Physical audit required to confirm.**
