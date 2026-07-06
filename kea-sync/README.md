# kea-sync

Periodic poller that reads active DHCP leases from the Kea DHCP4 REST API and syncs
subscriber IP addresses back to NetBox IPAM.

## How It Works

1. Every `POLL_INTERVAL_SECONDS` (default: 60), query Kea for all active leases via
   `lease4-get-all` on the Kea control agent HTTP API.
2. For each lease, extract `circuit-id` from relay-agent-info (Option 82, RouterOS 7.21+)
   and the relay `giaddr` (top-level field on the lease record).
3. Map `giaddr` (e.g. `100.65.X.11`) to a NetBox switch device via `primary_ip4`.
4. Map circuit-id `<interface>:<vid>` (hex-decoded ASCII) to a NetBox interface name
   (`ETH{N}`).
5. Walk the NetBox cable: switch interface → circuit termination → CX-Circuit → Tenant.
6. Upsert an IP address record in NetBox IPAM and associate it with the circuit.

## Network Addressing

Kea subnets use **CGNAT space** (`100.65.X.0/24`), one per building:
- Subnet ID = site number (id=1 → site 000001, id=36 → site for 2058 Union St, etc.)
- Pool: `.41–.250` per subnet; gateway at `.X.1`
- Relay IPs: `.X.11` (primary switch), `.X.12`/`.X.13` (multi-switch buildings)
- Essex (site 5001) is a special case: flat `100.64.36.0/22` CGNAT pool

## Circuit-ID Mapping

RouterOS 7.21+ sends Option 82 circuit-id as hex-encoded ASCII of `<interface>:<vid>`,
e.g. `6574686572333a3230` decodes to `ether3:20`.
The DHCP relay `giaddr` is the switch's management IP (`100.65.X.11`).

Resolution chain:
```
giaddr (100.65.X.11 — switch primary_ip4 in NetBox)
  → NetBox device with primary_ip4 = giaddr
    → interface named ETH{N}  (ether3 → ETH3)
      → cable → circuit termination Z
        → CX-Circuit
          → Tenant
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KEA_API_URL` | `http://172.27.209.248:8000` | Kea control agent (jumpB ZeroTier IP) |
| `KEA_API_USER` | `kea` | HTTP Basic Auth username for Kea API |
| `KEA_API_PASSWORD` | — | HTTP Basic Auth password (required, from `/etc/kea/kea-api-secret`) |
| `NETBOX_URL` | `http://172.27.48.233:8001` | NetBox instance URL |
| `NETBOX_TOKEN` | — | NetBox API token (required) |
| `POLL_INTERVAL_SECONDS` | `60` | Lease poll interval in seconds |
| `DRY_RUN` | `false` | Log changes without writing to NetBox |

## Run Locally

```bash
pip install -r requirements.txt
cp config/.env.example config/.env
# Edit config/.env and fill in KEA_API_PASSWORD and NETBOX_TOKEN
export $(grep -v '^#' config/.env | xargs)
python lease_poller.py
```

To get `KEA_API_PASSWORD`, read it from jumpB:
```bash
ssh jumpB sudo cat /etc/kea/kea-api-secret
# output is in htpasswd format: user:password
```

## Docker

```bash
docker build -t kea-sync .
docker run --env-file config/.env kea-sync
```

## Notes

- DHCP unicast renewals do NOT carry Option 82 circuit-id. Use Kea host reservations
  (keyed on circuit-id) rather than class-based assignment so reservations survive
  unicast renewal.
- The subscriber IP pools (`100.65.X.0/24`) must exist in NetBox IPAM before this
  poller can assign IPs meaningfully. Run
  `netbox-scripts/ipam/seed_subscriber_pools.py` first.
- The Kea control agent listens on `127.0.0.1:8000` on jumpB. It is reachable from
  other ZeroTier nodes at `172.27.209.248:8000`. The API requires HTTP Basic Auth;
  credentials are stored in `/etc/kea/kea-api-secret` (sudo required to read).
