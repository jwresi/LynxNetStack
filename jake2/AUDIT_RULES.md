# Audit Rules

## Status

This document is created in Phase 2 so the audit contract exists before code migration.

Implementation-level `# WHY:` tags will be added in Phases 3 and 4 when code is migrated.

## MAC CPE Population Rules

- A MAC populates `MAC CPE` only when live-on-port evidence exists.
- Controller mismatch alone must NOT populate `MAC CPE`.
- Switch-local MACs must NOT count as CPE evidence.
- Edge-port bridge-host evidence outranks generic switch-local sightings.
- Vilo snapshot and TAUC audit data are corroboration only.

## Row State Rules

- Green
  - correct device seen on correct port
- Yellow
  - device seen but placement is wrong
- Red
  - device not seen

## Switch Namespace Rules

- SW1 and SW2 are distinct namespaces.
- No interface collapsing across switches.
- No cross-switch fallback logic.

## MAC Bug Contract

### `_known_mac_bug_kind`

- Signature: `(str | None, str | None) -> str | None`
- Valid returns:
  - `"first_octet"`
  - `"last_octet"`
  - `None`
- Never returns `bool`
- Never raises on `None` input

### Exact Match

- `match_kind = "exact"`
- `inventory_mac_verification = "Match"`
- row state = green

### First Octet Bug

- `match_kind = "first_octet"`
- `inventory_mac_verification = "Bug-adjusted match"`
- row state = green
- implication includes explicit bug note

### Last Octet Bug

- `match_kind = "last_octet"`
- `inventory_mac_verification = "LAN-port MAC"`
- row state = yellow
- `notes = "MOVE CPE TO WAN PORT"`
- `action = "Move CPE to WAN/uplink port"`
- implication = CPE is plugged into LAN port

### No Match

- `inventory_mac_verification = "Mismatch"`

## Locked Strings

These strings are external contracts and must remain verbatim:

- `Match`
- `Bug-adjusted match`
- `LAN-port MAC`
- `Mismatch`
- `MOVE CPE TO WAN PORT`
- `MOVE CPE TO CORRECT UNIT`
- `WRONG UNIT`
- `UNKNOWN MAC ON PORT`

## Yellow Note Strings

All of these must be handled in color logic:

- `WRONG UNIT`
- `MOVE CPE TO CORRECT UNIT`
- `MOVE CPE TO WAN PORT`
- `UNKNOWN MAC ON PORT`

## Observability Requirement

Every row state must have a traceable explanation showing:

- what evidence was observed
- what rule was applied
- what conclusion was reached
- what was absent or ambiguous

When live evidence collection fails, the audit path must surface an explicit classified failure state instead of silently collapsing to `None` or empty evidence.

## Placeholder Implicit Knowledge: `jake_shared.py`

These items were identified in discovery and must be captured later with `# WHY:` tags and final docs:

- site aliases reflect operator language and common shorthand, not cosmetic alternate names
- site service profiles encode real operational topology differences
- Cambridge / site `000004` is G.hn over Positron and must not be reasoned about as GPON/OLT/fiber
- NYCHA / site `000007` is a switch-access TP-Link and Vilo site and must not inherit OLT assumptions
- OLT sites require ONU/optical reasoning that should not be collapsed into PPP-only summaries

## Placeholder Implicit Knowledge: `jake_audit_workbook.py`

These items were identified in discovery and are now captured in the migrated audit code with `# WHY:` tags:

- controller verification data is corroboration and must not override missing live-on-port evidence
- edge-port MAC evidence is more meaningful than generic switch-local MAC sightings
- controller mismatch alone cannot populate `MAC CPE`
- Vilo snapshot and TAUC audit are corroboration only
- live lookup failures must surface explicit classified failure state
- Vilo snapshot loading failures and other auxiliary evidence failures must not silently flatten into “no evidence”
