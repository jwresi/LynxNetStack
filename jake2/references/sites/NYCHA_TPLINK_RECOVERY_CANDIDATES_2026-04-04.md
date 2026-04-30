# NYCHA TP-Link Recovery Candidates 2026-04-04

This ranking now uses grounded local and live-controller evidence:

- `output/tauc_nycha_cpe_audit_latest.csv`
- existing TP-Link subscriber-join logic in the old Jake `mcp/jake_ops_mcp.py`
- local NYCHA-info MAC comparisons
- latest switch attribution already present in the audit
- live TAUC runtime reads from `get_tp_link_subscriber_join()`
- TAUC cloud `ONLINE` name-list checks

Important limit:

- TAUC runtime reads now work for resolved devices from this host
- but unresolved-name discovery is still incomplete, so names that do not resolve through local export or TAUC runtime remain investigation targets rather than proven offline units

## Tier 1: Best Recovery-First TP-Link Targets

These are the strongest current bring-up or field-investigation candidates because they remain unresolved after live TAUC checks.

- `NYCHA728EastNewYorkAve3K`
  - unit: `3K`
  - serial: `Y24A0X0002047`
  - MAC: `30:68:93:c1:ad:8e`
  - expected building: `000007.055`
  - interpretation:
    - grounded NYCHA unit identity
    - not in the current local online export
    - does not resolve through live TAUC runtime join from this host
    - good first real recovery candidate once a clean lane is available

- `NYCHA1144LenoxRd4F`
  - unit: `4F`
  - serial: `Y247138001004`
  - MAC: `3c:64:cf:44:3d:49`
  - expected building: `000007.003`
  - interpretation:
    - unresolved after live TAUC checks
    - better true investigation target than the units already proven online

- `NYCHA1145LenoxRd3B`
  - unit: `3B`
  - serial: `Y24A0X0002098`
  - MAC: `30:68:93:c1:ae:27`
  - expected building: `000007.004`
  - interpretation:
    - unresolved after live TAUC checks
    - better true investigation target than the units already proven online

Interpretation:

- these are the best targets to try first if the goal is “can we get a few to come up”
- they remain unresolved after live controller checks, which makes them better true recovery cases than the duplicate-MAC examples already proven healthy

## Tier 2: Duplicate-MAC Investigation Set At 000007.055

These are physically attributed to access ports, but the TAUC MAC and NYCHA-info MAC disagree in a way that looks like HC220 alternate-interface drift or local duplication.

### `000007.055.SW03`

- `7C`
  - `ether18`
  - serial `Y24A0N0000888`
  - TAUC MAC `30:68:93:a7:21:b0`
  - NYCHA-info MAC `30:68:93:a7:17:d5`

- `7E`
  - `ether24`
  - serial `Y24A0N0000881`
  - TAUC MAC `30:68:93:a7:0f:5c`
  - NYCHA-info MAC `30:68:93:a7:17:c0`

- `9H`
  - `ether34`
  - serial `Y24A0X0002169`
  - TAUC MAC `30:68:93:a7:14:ff`
  - NYCHA-info MAC `30:68:93:c1:ae:fc`

- `9J`
  - `ether36`
  - serial `Y2490C7002120`
  - TAUC MAC `30:68:93:a7:14:a8`
  - NYCHA-info MAC `dc:62:79:9d:c2:e5`

- `10B`
  - `ether40`
  - serial `Y24A0X0000616`
  - TAUC MAC `30:68:93:a7:17:03`
  - NYCHA-info MAC `30:68:93:c1:9c:c9`

- `10D`
  - `ether44`
  - serial `Y24A0X0001877`
  - TAUC MAC `30:68:93:c1:ac:1a`
  - NYCHA-info MAC `30:68:93:c1:ab:90`

- `10E`
  - `ether45`
  - serial `Y24A0X0002154`
  - TAUC MAC `30:68:93:c1:9c:96`
  - NYCHA-info MAC `30:68:93:c1:ae:cf`

- `10F`
  - `ether46`
  - serial `Y24A0X0001691`
  - TAUC MAC `30:68:93:c1:9d:20`
  - NYCHA-info MAC `30:68:93:c1:a9:62`

### `000007.055.SW04`

- `7L`
  - `ether3`
  - serial `Y24A0X0002147`
  - TAUC MAC `30:68:93:a7:21:68`
  - NYCHA-info MAC `30:68:93:c1:ae:ba`

- `7F`
  - `ether4`
  - serial `Y24A0X0000650`
  - TAUC MAC `30:68:93:a7:0f:44`
  - NYCHA-info MAC `30:68:93:c1:9d:2f`

- `8C`
  - `ether5`
  - serial `Y24A0N0000689`
  - TAUC MAC `30:68:93:c1:9c:90`
  - NYCHA-info MAC `30:68:93:a7:15:80`

- `8H`
  - `ether7`
  - serial `Y24A0N0000771`
  - TAUC MAC `30:68:93:c1:ae:e1`
  - NYCHA-info MAC `30:68:93:a7:16:76`

- `8G`
  - `ether8`
  - serial `Y24A0N0000795`
  - TAUC MAC `30:68:93:a7:20:78`
  - NYCHA-info MAC `30:68:93:a7:16:be`

- `8F`
  - `ether9`
  - serial `Y24A0N0000359`
  - TAUC MAC `30:68:93:a7:1c:55`
  - NYCHA-info MAC `30:68:93:a7:11:a2`

- `9E`
  - `ether12`
  - serial `Y2490C7002065`
  - TAUC MAC `30:68:93:a7:0e:fc`
  - NYCHA-info MAC `dc:62:79:9d:c2:40`

Interpretation:

- these are not the best first recovery targets
- they are the best duplicate-MAC investigation block
- Jake should treat them first as:
  - one HC220 with alternate-interface MAC drift
  - or a bridge/dirty-segment case
  - not automatically as “wrong customer on wrong port”

Live grounded examples already confirmed healthy:

- `7C`
  - TAUC runtime says `ONLINE`
  - PPPoE `Connected`
  - live controller MAC `30:68:93:a7:17:d5`
- `10D`
  - TAUC runtime says `ONLINE`
  - PPPoE `Connected`
  - live controller MAC `30:68:93:c1:ab:90`

Additional healthy-but-stale-audit examples outside the duplicate block:

- `8D`
  - TAUC runtime says `ONLINE`
  - PPPoE `Connected`
  - live controller MAC `30:68:93:a7:22:7c`
- `4D`
  - TAUC runtime says `ONLINE`
  - PPPoE `Connected`
  - live controller MAC `30:68:93:c1:ab:c3`

## Tier 3: Unknown-Expected But Physically Seen

- `NYCHA955RutlandUnit1H`
  - serial: `Y24A0X0002261`
  - MAC: `30:68:93:c1:b0:10`
  - actual sighting: `000007.058.SW01 ether8`
  - classification: `access_seen_unknown_expected`

Interpretation:

- this is not a first recovery target
- it is a data-quality target
- Jake should treat it as a physically seen HC220 whose expected-side metadata is incomplete

## Operational Read

If the goal is to test a few TP-Link units and see if they will come up, start with:

1. `000007.055` unit `3K`
2. `000007.003` unit `4F`
3. `000007.004` unit `3B`

If the goal is to sort out duplicate-MAC issues, start with:

1. `000007.055.SW03`
   - `7C`, `7E`, `9H`, `9J`, `10B`, `10D`, `10E`, `10F`
2. `000007.055.SW04`
   - `7L`, `7F`, `8C`, `8H`, `8G`, `8F`, `9E`

## Controller Readout

Already confirmed live and healthy through TAUC runtime:

- `NYCHA728EastNewYorkAve8D`
  - `network_id=10987879005189`
  - `serial=Y24A0N0001797`
  - `MAC=30:68:93:a7:22:7c`
  - WAN: `PPPoE Connected`
  - username: `NYCHA728EastNewYorkAve8D`
- `NYCHA1142LenoxRd4D`
  - `network_id=11391979217929`
  - `serial=Y24A0X0001894`
  - `MAC=30:68:93:c1:ab:c3`
  - WAN: `PPPoE Connected`
  - username: `NYCHA1142LenoxRd4D`
- `NYCHA728EastNewYorkAve7C`
  - `network_id=10987878743324`
  - `serial=Y24A0N0000888`
  - `MAC=30:68:93:a7:17:d5`
  - WAN: `PPPoE Connected`
  - username: `NYCHA728EastNewYorkAve7C`
- `NYCHA728EastNewYorkAve10D`
  - `network_id=10987879398407`
  - `serial=Y24A0X0001877`
  - `MAC=30:68:93:c1:ab:90`
  - WAN: `PPPoE Connected`
  - username: `NYCHA728EastNewYorkAve10D`

Still unresolved from this runtime:

- `NYCHA728EastNewYorkAve3K`
- `NYCHA1144LenoxRd4F`
- `NYCHA1145LenoxRd3B`
