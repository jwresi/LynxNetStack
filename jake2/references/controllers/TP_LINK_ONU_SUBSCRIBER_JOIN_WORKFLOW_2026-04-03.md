## TP-Link ONU To Subscriber Join Workflow

Use this when Jake needs to answer:
- which subscriber is behind this `TPLG-...` ONU
- which ONU is serving this TP-Link HC220 subscriber
- why a TP-Link CPE and OLT do not line up cleanly

### Core rule
Do not assume a direct join exists just because both sides are TP-Link.

The subscriber-side HC220 identity and the OLT-side ONU identity are often exposed through different identifiers:
- subscriber side: `networkName`, `networkId`, HC220 serial like `Y24...`, CPE MAC like `30:68:93:...`
- OLT side: ONU serial like `TPLG-...`, GPON port, ONU id, optical state

Jake should only claim a deterministic join when the evidence chain is explicit.

### Evidence order
1. Resolve the local subscriber row from the freshest local online CPE export.
2. Pull TAUC runtime for that exact subscriber:
   - `devices/tr`
   - `devices/tr/clients`
   - `network-map/.../devices`
   - `network-map/.../clients/tr/v3`
   - `internet/waninfo`
3. Generate HC220 adjacent MAC candidates:
   - exact MAC
   - first octet alternate like `30:` -> `32:`
   - last octet `-1`, `0`, `+1`
4. Probe every site OLT MAC table with:
   - `show mac address-table address <mac>`
5. If starting from `TPLG-...`, resolve live ONU placement first:
   - scan `show ont info gpon 1/0/<n> detail`
   - then run `show ont info gpon <pon> ont <onu>`

### How to interpret the results

Positive join:
- TAUC gives the subscriber MAC
- the OLT MAC table learns that MAC or an adjacent HC220 variant
- the returned OLT row points to a GPON or service location

Negative OLT MAC result:
- if the exact MAC and the adjacent HC220 variants all return `Specified entry is NULL`,
  Jake should say that the OLT is not currently exposing the HC220 WAN-side identity in the bridge table
- that is a real negative signal, not just “not checked”

### What causes the MAC issues

There are multiple causes, and Jake should not collapse them into one theory:

1. Multi-interface vendor identities
- HC220 devices can present a subscriber-facing/base MAC and a WAN-side alternate MAC
- a common pattern is first-octet drift such as `30:` vs `32:`

2. Adjacent interface MAC allocation
- some devices allocate interface MACs sequentially
- this is why last-octet `+/-1` often matters

3. WAN/LAN bridging or leakage
- if a CPE is bridged or partially misconfigured, the access network may see the “wrong” hardware-side MAC

4. Wrong-port or mislabeled patching
- if the expected subscriber MAC is missing but an adjacent MAC is on a neighboring port, that can indicate a wrong-port or labeling issue

5. OLT visibility limits
- even when the subscriber is online, the OLT may not expose the HC220 MAC in the expected MAC table
- in that case Jake should say the join is blocked by missing edge exposure, not invent a unit mapping

### Required output style
Jake should report:
1. what identifier he started with
2. what subscriber-side row was found
3. what TAUC runtime confirmed
4. what MAC variants were tested
5. which OLTs were probed
6. whether there was a direct OLT hit
7. if not, what specifically is still missing
