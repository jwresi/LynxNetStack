# LynxMSP DHCP Wiring 2026-04-09

Jake's live DHCP lease correlation is only fully usable when at least one real LynxMSP or lynxdhcp source is wired on this host.

## Accepted Inputs

- `LYNXMSP_API_URL`
- `LYNXMSP_DB_PATH`
- `LYNXDHCP_STATE_PATH`

## Current Candidate Order

DB candidates:

- env `LYNXMSP_DB_PATH`
- `./LynxMSP/data/lynxcrm.db`
- `./LynxMSP/backend/lynxcrm.db`

API candidates:

- env `LYNXMSP_API_URL`
- env `LYNX_API_URL`
- `http://127.0.0.1:8000`
- `http://127.0.0.1:8010`

DHCP snapshot candidates:

- env `LYNXDHCP_STATE_PATH`
- `./lynxdhcp/data/state.json`

## Why Jake Was Falling Back Badly

If no real path is present:

- there is no local LynxMSP DB
- there is no local `lynxdhcp` state file
- no explicit `LYNXMSP_API_URL` is set
- Jake falls back to localhost API probes and reports DHCP unavailable

## Verification

Run:

```bash
python3 scripts/check_lynxmsp_wiring.py
```

This reports:

- current env values
- candidate DB/API/state paths
- resolved DB/state paths
- API reachability
- active blockers
- recommended next actions

## Operator Impact

Without real LynxMSP wiring, Jake can still reason from:

- Splynx
- RouterOS
- OLT
- local subscriber exports

But Jake cannot fully prove live DHCP lease state or exact DHCP-based customer identity.
