# kea-sync

Periodic poller that reads active DHCP leases from the Kea DHCP4 REST API and syncs
subscriber IP addresses back to NetBox IPAM.

## How It Works

1. Every `POLL_INTERVAL_SECONDS` (default: 60), query Kea for all active leases.
2. For each lease, extract `circuit-id` from the client-id / relay-agent-info.
3. Map circuit-id format `<interface>:<vid>` (RouterOS 7.21+) + relay `giaddr` to a
   NetBox switch interface via the switch's management IP.
4. Walk the NetBox cable: switch interface → circuit termination → CX-Circuit → Tenant.
5. Upsert an IP address record in NetBox IPAM and associate it with the circuit.

## Circuit-ID Mapping

RouterOS 7.21+ sends Option 82 circuit-id as `<interface>:<vid>`, e.g. `ether3:20`.
The DHCP relay `giaddr` is the switch's management IP on VLAN 10.

Resolution chain:
```
giaddr (switch mgmt IP)
  → NetBox device with primary_ip4 = giaddr
    → interface named ETH{N}  (ether3 → ETH3)
      → cable → circuit termination Z
        → CX-Circuit
          → Tenant
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KEA_API_URL` | `http://172.27.28.50:8000` | Kea control agent base URL |
| `NETBOX_URL` | `http://172.27.48.233:8001` | NetBox instance URL |
| `NETBOX_TOKEN` | — | NetBox API token (required) |
| `POLL_INTERVAL_SECONDS` | `60` | Lease poll interval |
| `DRY_RUN` | `false` | Log changes without writing to NetBox |

## Run Locally

```bash
pip install -r requirements.txt
export NETBOX_TOKEN=your_token_here
python lease_poller.py
```

## Docker

```bash
docker build -t kea-sync .
docker run -e NETBOX_TOKEN=xxx -e KEA_API_URL=http://172.27.28.50:8000 kea-sync
```

## Notes

- DHCP unicast renewals do NOT carry Option 82 circuit-id. Use Kea host reservations
  (keyed on circuit-id) rather than class-based assignment so reservations survive
  unicast renewal.
- The subscriber IP pools `10.0.8.0/24` through `10.0.14.0/24` must exist in NetBox
  IPAM before this poller can assign IPs meaningfully. Run
  `netbox-scripts/ipam/seed_subscriber_pools.py` first.
