# kea-sync

Polls the Kea DHCP4 control agent for active leases and syncs subscriber IP
addresses into NetBox IPAM, linking each IP to its CX-Circuit and Tenant.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Setup on jumpB](#setup-on-jumpb)
4. [Configuration](#configuration)
5. [Running](#running)
6. [Docker (production)](#docker-production)
7. [Verifying It Works](#verifying-it-works)
8. [How the Lease Resolution Works](#how-the-lease-resolution-works)
9. [Dry-Run Mode](#dry-run-mode)
10. [Troubleshooting](#troubleshooting)
11. [Notes and Constraints](#notes-and-constraints)

---

## Architecture

kea-sync **must run on jumpB** (the same host as Kea). The Kea control agent
only binds to `127.0.0.1:8000` and does not accept remote connections. No
credentials are required from localhost.

```
┌─────────────────────────────────────────────────────────────┐
│  jumpB                                                      │
│                                                             │
│   ┌──────────────────┐    HTTP POST      ┌──────────────┐  │
│   │   kea-sync       │ ───────────────▶  │  kea-dhcp4   │  │
│   │  lease_poller.py │  127.0.0.1:8000   │ control agent│  │
│   └────────┬─────────┘  (no auth)        └──────────────┘  │
│            │                                                │
└────────────┼────────────────────────────────────────────────┘
             │  HTTPS / NetBox REST API
             ▼
      ┌──────────────┐
      │   NetBox     │  172.27.48.233:8001
      │  (IPAM sync) │
      └──────────────┘
```

Every 60 seconds (configurable), kea-sync:

1. Fetches all active leases from Kea via `lease4-get-all`
2. For each lease, resolves the subscriber circuit from relay metadata (Option 82)
3. Upserts the subscriber IP in NetBox IPAM, linked to the CX-Circuit and Tenant

---

## Prerequisites

**On jumpB:**

- Python 3.9+ (`python3 --version`)
- pip (`python3 -m pip --version`)
- Network access to NetBox at `172.27.48.233:8001`
- A valid NetBox API token

**In NetBox (must exist before first run):**

- Subscriber IP pools (`100.65.X.0/24`) seeded in IPAM
  → run `netbox-scripts/ipam/seed_subscriber_pools.py` if not done
- Switch devices with `primary_ip4` set to their relay IP (`100.65.X.11`)
- CX-Circuits linked to switch interfaces via NetBox cables

To confirm Kea is running on jumpB:

```
$ ssh jumpB
jumpB$ docker ps | grep kea
```

Expected output:

```
CONTAINER ID   IMAGE          COMMAND                  CREATED        STATUS
a3f9d2e1b4c8   kea-dhcp4      "/entrypoint.sh kea-…"   2 weeks ago    Up 2 weeks
```

To confirm the control agent is listening:

```
jumpB$ curl -s -X POST http://127.0.0.1:8000/ \
  -H 'Content-Type: application/json' \
  -d '{"command":"version-get","service":["dhcp4"]}' | python3 -m json.tool
```

Expected output (version may differ):

```json
[
  {
    "result": 0,
    "text": "2.4.1 (tarball)",
    "arguments": {
      "extended": "..."
    }
  }
]
```

If you get `Connection refused`, Kea is not running. If you get `401`, you are
hitting the external interface — double-check you are on jumpB itself.

---

## Setup on jumpB

### 1. Clone the repo (first time only)

```
jumpB$ git clone https://github.com/jwresi/LynxNetStack.git /opt/lynxnetstack
jumpB$ cd /opt/lynxnetstack/kea-sync
```

If the repo already exists, pull latest:

```
jumpB$ cd /opt/lynxnetstack
jumpB$ git pull
jumpB$ cd kea-sync
```

### 2. Create a virtual environment

```
jumpB$ python3 -m venv .venv
jumpB$ source .venv/bin/activate
(.venv) jumpB$ pip install -r requirements.txt
```

Successful install looks like:

```
Successfully installed certifi-2024.x.x charset-normalizer-3.x.x \
  idna-3.x requests-2.31.x urllib3-2.x.x
```

### 3. Create the config file

```
(.venv) jumpB$ cp config/.env.example config/.env
(.venv) jumpB$ nano config/.env
```

The only required change is setting `NETBOX_TOKEN`. See [Configuration](#configuration).

---

## Configuration

Edit `config/.env`:

```ini
# Kea DHCP4 control agent — localhost on jumpB, no auth required
KEA_API_URL=http://127.0.0.1:8000

# NetBox
NETBOX_URL=http://172.27.48.233:8001
NETBOX_TOKEN=<your-token-here>

# How often to poll (seconds)
POLL_INTERVAL_SECONDS=60

# Set true to log without writing anything to NetBox
DRY_RUN=false
```

### Getting your NetBox API token

In NetBox, go to **Admin → API Tokens** (or your user profile → API Tokens):

```
NetBox UI path:
  http://172.27.48.233:8001 → top-right user menu
  → Profile → API Tokens → + Add
```

Copy the token — it is only shown once. Paste it as `NETBOX_TOKEN` in `config/.env`.

Alternatively, if you already have a token in another component:

```
jumpB$ cat /opt/lynxnetstack/jake2/config/.env | grep NETBOX_TOKEN
```

Use that same token — it has the correct permissions.

### Environment variable reference

| Variable | Default | Required | Description |
|---|---|---|---|
| `KEA_API_URL` | `http://127.0.0.1:8000` | No | Kea control agent. Do not change unless tunneling. |
| `NETBOX_URL` | `http://172.27.48.233:8001` | No | NetBox instance |
| `NETBOX_TOKEN` | — | **Yes** | NetBox API token |
| `POLL_INTERVAL_SECONDS` | `60` | No | Seconds between lease polls |
| `DRY_RUN` | `false` | No | If `true`, logs all changes but writes nothing |

---

## Running

### Load env and start

```
jumpB$ cd /opt/lynxnetstack/kea-sync
jumpB$ source .venv/bin/activate
(.venv) jumpB$ export $(grep -v '^#' config/.env | xargs)
(.venv) jumpB$ python lease_poller.py
```

Startup log (healthy):

```
2026-07-06 14:23:01,412 [INFO] kea-sync starting. Kea=http://127.0.0.1:8000 NetBox=http://172.27.48.233:8001 interval=60s
2026-07-06 14:23:01,891 [INFO] Fetched 247 leases from Kea
2026-07-06 14:23:04,221 [INFO] Creating IP 100.65.3.142/32 -> circuit CX-0042 tenant savoy
2026-07-06 14:23:04,890 [INFO] Updating IP 100.65.7.88/32 -> circuit CX-0019 tenant essex
...
2026-07-06 14:23:12,104 [INFO] Poll complete: 247 leases processed
```

Press `Ctrl+C` to stop.

### Run in background with nohup

For a persistent session that survives SSH disconnect:

```
jumpB$ cd /opt/lynxnetstack/kea-sync
jumpB$ source .venv/bin/activate
jumpB$ export $(grep -v '^#' config/.env | xargs)
jumpB$ nohup python lease_poller.py >> /var/log/kea-sync.log 2>&1 &
jumpB$ echo $!   # note the PID
```

Check it is running:

```
jumpB$ tail -f /var/log/kea-sync.log
```

Stop it:

```
jumpB$ kill <PID>
```

### Run as a systemd service (recommended for production)

Create `/etc/systemd/system/kea-sync.service`:

```ini
[Unit]
Description=kea-sync lease poller
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/lynxnetstack/kea-sync
EnvironmentFile=/opt/lynxnetstack/kea-sync/config/.env
ExecStart=/opt/lynxnetstack/kea-sync/.venv/bin/python lease_poller.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:

```
jumpB$ sudo systemctl daemon-reload
jumpB$ sudo systemctl enable kea-sync
jumpB$ sudo systemctl start kea-sync
jumpB$ sudo systemctl status kea-sync
```

Expected status output:

```
● kea-sync.service - kea-sync lease poller
     Loaded: loaded (/etc/systemd/system/kea-sync.service; enabled)
     Active: active (running) since Mon 2026-07-06 14:30:00 UTC; 2min ago
   Main PID: 12345 (python)
```

View live logs:

```
jumpB$ sudo journalctl -u kea-sync -f
```

---

## Docker (production)

Build and run from the `kea-sync/` directory on jumpB:

```
jumpB$ cd /opt/lynxnetstack/kea-sync
jumpB$ docker build -t kea-sync .
jumpB$ docker run -d \
    --name kea-sync \
    --restart unless-stopped \
    --network host \
    --env-file config/.env \
    kea-sync
```

`--network host` is required so the container can reach `127.0.0.1:8000` (the
Kea control agent on the jumpB host).

Check logs:

```
jumpB$ docker logs -f kea-sync
```

Stop / restart:

```
jumpB$ docker stop kea-sync
jumpB$ docker start kea-sync
```

---

## Verifying It Works

### Check a specific lease end-to-end

Pick a site you know is active (e.g. savoy = site 000002, relay `100.65.2.11`).

**Step 1 — confirm Kea has leases for that subnet:**

```
jumpB$ /opt/kea-dhcp/list-leases | grep '"giaddr": "100.65.2.11"' | head -3
```

You should see lease records with `"ip-address"` in `100.65.2.0/24`.

**Step 2 — confirm the NetBox device exists with that relay IP:**

```
$ curl -s "http://172.27.48.233:8001/api/dcim/devices/?primary_ip=100.65.2.11" \
  -H "Authorization: Token <your-token>" | python3 -m json.tool | grep '"name"'
```

Expected: a device name like `000002.001.SW01`.

**Step 3 — after one poll cycle, check IPAM in NetBox:**

```
NetBox UI:
  IPAM → IP Addresses → filter by "100.65.2." in the search box
```

Each synced IP will have a description like:

```
kea-sync | circuit=CX-0003 | mac=aa:bb:cc:dd:ee:ff
```

### Quick smoke test with DRY_RUN

Run one poll in dry-run mode to see what would be written without touching NetBox:

```
jumpB$ DRY_RUN=true NETBOX_TOKEN=<token> python lease_poller.py
```

Look for `[INFO] Creating IP` and `[INFO] Updating IP` lines — these are the
writes that would have happened. No `[ERROR]` lines means the resolution chain
is working.

---

## How the Lease Resolution Works

Each DHCP lease from Kea contains:

```
{
  "ip-address": "100.65.3.142",      ← subscriber IP to upsert in NetBox IPAM
  "hw-address": "aa:bb:cc:dd:ee:ff", ← MAC (stored in description)
  "giaddr": "100.65.3.11",           ← relay agent IP = switch primary_ip4 in NetBox
  "user-context": {
    "ISC": {
      "relay-agent-info": {
        "circuit-id": "6574686572333a3230"  ← hex-encoded "ether3:20"
      }
    }
  }
}
```

Resolution chain:

```
giaddr = 100.65.3.11
  │
  ▼
NetBox: dcim/devices/?primary_ip=100.65.3.11
  → device: 000003.001.SW01  (id=88)
  │
  ▼
circuit-id hex "6574686572333a3230" → decode → "ether3:20" → ETH3
NetBox: dcim/interfaces/?device_id=88&name=ETH3
  → interface id=441
  │
  ▼
NetBox: dcim/cables/?termination_a_id=441
  → cable id=12
  │
  ▼
NetBox: circuits/circuit-terminations/?cable_id=12
  → circuit termination → circuit: CX-0051 (tenant: Savoy Gardens)
  │
  ▼
NetBox: ipam/ip-addresses/?address=100.65.3.142/32
  → exists? PATCH description + tenant
  → missing? POST new IP record
```

Leases with no `circuit-id` (unicast renewals, fixed-address hosts) are skipped
with a DEBUG log — they cannot be resolved to a circuit without relay metadata.

---

## Dry-Run Mode

Set `DRY_RUN=true` in `config/.env` (or as an env var) to run kea-sync in
read-only mode. All NetBox writes are skipped; the log shows what *would* happen:

```
2026-07-06 14:45:01,112 [INFO] DRY_RUN=true — no writes will be made to NetBox
2026-07-06 14:45:01,882 [INFO] Fetched 247 leases from Kea
2026-07-06 14:45:04,210 [INFO] Creating IP 100.65.3.142/32 -> circuit CX-0042 tenant savoy
2026-07-06 14:45:04,891 [INFO] Updating IP 100.65.7.88/32 -> circuit CX-0019 tenant essex
2026-07-06 14:45:12,103 [INFO] Poll complete: 247 leases processed
```

Use dry-run for:
- Validating after a NetBox data migration
- Checking a new site's cable/circuit wiring before going live
- Testing a config change without affecting IPAM

---

## Troubleshooting

### `RuntimeError: NETBOX_TOKEN environment variable is required`

The env file was not loaded. Make sure you ran:

```
export $(grep -v '^#' config/.env | xargs)
```

Or, if using Docker, that `--env-file config/.env` is on the `docker run` command.

### `Failed to fetch Kea leases: Connection refused`

kea-sync is not running on jumpB, or you are running it from a different host.
The control agent only listens on `127.0.0.1`. Confirm:

```
jumpB$ curl http://127.0.0.1:8000/ -X POST \
  -H 'Content-Type: application/json' \
  -d '{"command":"list-commands","service":["dhcp4"]}'
```

If that fails, Kea or its control agent is down:

```
jumpB$ docker ps | grep kea
jumpB$ docker logs kea-dhcp4 --tail 50
```

### `Fetched 0 leases from Kea`

Kea responded but returned no leases. Check:

```
jumpB$ /opt/kea-dhcp/list-leases | python3 -m json.tool | head -30
```

If `list-leases` also returns 0, the DHCP service may not have active leases
yet (e.g. after a Kea restart before clients renew). Wait for clients to renew
or check `kea-dhcp4` logs.

### `NetBox GET dcim/devices/ failed: 401`

Bad or expired `NETBOX_TOKEN`. Generate a new token in NetBox and update `config/.env`.

### `No NetBox device found for giaddr 100.65.X.11`

The switch at that site does not have `primary_ip4` set in NetBox, or it is set
to a different IP. In NetBox:

```
DCIM → Devices → search for the building → check Primary IPv4 field
```

It must be set to exactly `100.65.X.11/24` (with prefix length). The poller
strips the prefix when matching.

### `No NetBox interface ETH3 on device 000003.001.SW01`

The interface exists in RouterOS as `ether3` but has not been created in NetBox,
or it was created with a different name. NetBox interface names must follow
`ETH{N}` format (e.g. `ETH3`, not `ether3`). Check in NetBox:

```
DCIM → Devices → [device name] → Interfaces tab
```

### IP records not linked to correct Tenant

The cable from the switch interface to the circuit termination may be missing or
mis-wired in NetBox. Check:

```
DCIM → Devices → [device] → Interfaces → [ETH3] → Connected Endpoints
```

There should be a cable connecting the interface to a Circuit Termination. If
the "Connected Endpoints" column is empty, the cable is missing.

---

## Notes and Constraints

- **Unicast renewals skip circuit-id.** DHCP unicast renewals (after initial
  lease) do not carry Option 82. kea-sync silently skips these leases — they
  can only be resolved if Kea has a host reservation keyed on circuit-id.

- **100.65.0.0/10 CGNAT space.** Subscriber IPs are not routable on the public
  internet. The `/32` records in NetBox IPAM are documentation only — they track
  which subscriber has which IP at any given time.

- **Essex (site 5001) uses a flat pool** (`100.64.36.0/22`) rather than a per-
  building `/24`. The resolution logic is the same; only the subnet differs.

- **Do not restart Kea with active leases.** Use the control agent config-reload
  instead: `{"command":"config-reload","service":["dhcp4"]}` via the API.

- **NetBox version is pinned to 4.1.11.** Do not upgrade NetBox without checking
  all plugin compatibility first (see CLAUDE.md).

- **Subscriber IP pools must be pre-seeded.** Run
  `netbox-scripts/ipam/seed_subscriber_pools.py` before the first production
  run, or IP upserts will succeed but sit in IPAM without a parent prefix.
