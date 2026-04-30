# LynxDHCP

Go prototype for an ISP operations and NMS platform built around DHCP Option 82, relay domains, topology snapshots, and Stripe-first billing defaults.

## Why this shape

- Combines the broad ISP/MSP operating surface from `LynxMSP`
- Pulls the evidence-first network posture from `lynxnms`
- Defaults to DHCP Option 82 subscriber identity instead of PPPoE
- Keeps install friction low with a single Go web service and Docker

## Why this direction

- Go keeps deployment simple: one binary, one container, low memory, easy cross-platform builds
- The web UI is served directly by the Go app, which avoids a separate frontend build chain for early product iteration
- JSON-backed persistence keeps the prototype stateful without forcing a database choice too early
- Option 82 is modeled as the default subscriber identity workflow, which better matches relay, VLAN, and access-node operations than PPPoE-first assumptions

## Included in this prototype

- Overview dashboard
- Subscriber table with Option 82 fields
- Subscriber provisioning form
- Relay-domain and topology panel
- Findings queue
- Findings acknowledgement
- Stripe billing posture panel
- Change window queue
- Change approval action
- Persistent activity log
- Mobile-friendly terminal-inspired UI

## Persistence

- State is stored in `data/state.json`
- Override with `APP_STATE_PATH=/path/to/state.json`

## Run locally

```bash
docker compose up --build
```

Open `http://localhost:8080`.
