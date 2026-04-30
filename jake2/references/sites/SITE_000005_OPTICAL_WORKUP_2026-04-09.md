# Site 000005 Optical Workup

As of 2026-04-09, `000005` reads like an optical cleanup site, not a headend or router outage.

## Current Read

- Online customers: `333`
- Active alerts: `43`
- Outliers: `0`
- Tracked devices: `4`

## Active Optical Shape

- OLTs with active optics alarms: `000005.OLT1`, `000005.OLT2`, `000005.OLT3`
- Top optical cluster: `000005.OLT1 PON 4`
  - critical: `1`
  - low: `3`
  - worst: `-30.97 dBm`
- Secondary urgent clusters:
  - `000005.OLT1 PON 8` with `1` critical, worst `-31.55 dBm`
  - `000005.OLT2 PON 6` with `24` low alarms, worst `-29.59 dBm`

## Working Punch List

- OLT: `000005.OLT1` has optics alarms on PON `1, 2, 3, 4, 8`
- OLT: `000005.OLT2` has optics alarms on PON `1, 2, 3, 4, 6`
- OLT: `000005.OLT3` has optics alarms on PON `3, 4`
- PON: work `000005.OLT1 PON 4` first
- ONU/ONT serials on the top path include:
  - `TPLG-D0380696`
  - `TPLG-D0380622`
  - `TPLG-D038061E`
  - `TPLG-D03803B2`

## Operator Interpretation

- This does not currently read like a site-core outage.
- The strongest current owner is `Fiber/OLT team`.
- `000005.OLT1 PON 4` is the first path Jake should name when asked what to fix first.
- `000005.OLT2 PON 6` matters because the count is large, even though it is not the top critical cluster.

## Good Follow-Up Questions

- `what needs to be fixed at 000005?`
- `which PON port on 000005.OLT1 has the low power?`
- `which customers are affected by 000005.OLT1 PON 4?`
- `show the light levels on 000005`
