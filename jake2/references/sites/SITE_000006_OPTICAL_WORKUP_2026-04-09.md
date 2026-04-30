# Site 000006 Optical Workup

As of 2026-04-09, `000006` is also an optical cleanup site. The evidence does not point to a router or site-core outage first.

## Current Read

- Online customers: `140`
- Active alerts: `71`
- Outliers: `0`
- Tracked devices: `4`

## Active Optical Shape

- OLTs with active optics alarms: `000006.OLT01`, `000006.OLT02`
- Top optical cluster: `000006.OLT01 PON 3`
  - critical: `1`
  - low: `7`
  - worst: `-30.97 dBm`
- Heaviest low-light concentrations:
  - `000006.OLT02 PON 5` with `10` low alarms, worst `-7.92 dBm`
  - `000006.OLT02 PON 6` with `10` low alarms, worst `-7.34 dBm`

## Working Punch List

- OLT: `000006.OLT01` has optics alarms on PON `1, 2, 3, 4, 5`
- OLT: `000006.OLT02` has optics alarms on PON `1, 2, 3, 4, 5, 6, 7, 8`
- PON: work `000006.OLT01 PON 3` first
- ONU/ONT serials on the top path include:
  - `TPLG-93EBA7BE`
  - `TPLG-93EBA67E`
  - `TPLG-93EBA7BB`
  - `TPLG-93EBA7CB`

## Operator Interpretation

- The strongest current owner is `Fiber/OLT team`.
- The top path by severity is `000006.OLT01 PON 3`.
- The broader cleanup pressure is on `000006.OLT02`, especially PON `5` and `6`, because they carry many low-light alarms even without a current critical count.
- Jake should distinguish between the top critical cluster and the broadest low-light work queue.

## Good Follow-Up Questions

- `what needs to be fixed at 000006?`
- `which PON port on 000006.OLT01 has the low power?`
- `which customers are affected by 000006.OLT01 PON 3?`
- `show the light levels on 000006`
