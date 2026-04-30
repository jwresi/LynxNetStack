# IPoE Migration Runbook

Cutover procedure for moving NYCHA subscribers from PPPoE to IPoE/DHCP (Option 82).

## Prerequisites

Before cutting over ANY building:

- [ ] All switches in the building are on RouterOS 7.21.3+
- [ ] Kea DHCP4 is deployed and running on 172.27.28.50
- [ ] Kea DHCP4 control agent is reachable: `curl -X POST http://172.27.28.50:8000/ -d '{"command":"status-get","service":["dhcp4"]}'`
- [ ] CX-Circuits are populated in NetBox for all units in the building
- [ ] Subscriber IPAM pools (10.0.8.0/24 – 10.0.14.0/24) exist in NetBox
- [ ] kea-sync poller is running and successfully writing IPs to NetBox (verify: check a test lease)
- [ ] Hardware offload is OFF on all building switches (it is OFF site-wide — confirm before proceeding)
- [ ] tikfig has rendered the IPoE relay config for this building's switch(es)

## Per-Building Cutover Steps

### Step 1 — Verify switch firmware

```bash
# Via Jake2:
cd jake2
./jake --serve
# Query: "what firmware is running on 000007.001.SW01"
```

All switches in the building must be on 7.21.3+. If any are on 7.14.x, upgrade first.

### Step 2 — Create Kea host reservations for the building

For each subscriber unit, create a host reservation in Kea keyed on circuit-id:

```json
{
  "command": "reservation-add",
  "service": ["dhcp4"],
  "arguments": {
    "reservation": {
      "circuit-id": "65746865723320",
      "ip-address": "10.0.8.45",
      "subnet-id": 1,
      "hostname": "000007-001-1B"
    }
  }
}
```

Note: circuit-id is hex-encoded ASCII of `ether3:20`. Script TBD in kea-sync/scripts/.

### Step 3 — Push DHCP relay config to building switch

Using tikfig to render the relay config:

```bash
cd tikfig
curl -X POST http://localhost:8080/api/render \
  -H 'Content-Type: application/json' \
  -d '{"device_name": "000007.001.SW01", "template": "switch"}'
```

Review the rendered config, then push via ssh_mcp (propose → human approves → execute):

```json
{
  "name": "propose_config_change",
  "arguments": {
    "device_name": "000007.001.SW01",
    "commands": ["<rendered relay config lines>"],
    "reason": "IPoE migration: enable DHCP relay on VLAN 20",
    "backup_command": "/ip dhcp-relay print",
    "verify_command": "/ip dhcp-relay print",
    "requested_by": "operator"
  }
}
```

### Step 4 — Test DHCP relay

Plug in a test CPE on an unused port. Verify:
1. CPE gets a DHCP lease from Kea
2. `circuit-id` appears in Kea lease logs with correct `ether{N}:20` format
3. kea-sync resolves the lease to the correct NetBox Tenant
4. IP appears in NetBox IPAM linked to the Tenant

### Step 5 — Cut subscribers over (per unit)

For each unit:
1. PPPoE session will drop when subscriber router reboots or PPPoE disconnects
2. CPE should auto-request DHCP lease
3. Verify connectivity: ping subscriber IP from router

Do NOT force disconnect all subscribers simultaneously. Roll building by building.

### Step 6 — Update NetBox site custom field

After the full building (not just test units) is confirmed working:

```bash
# Patch site 000007 custom field via NetBox API
curl -X PATCH http://172.27.48.233:8001/api/dcim/sites/<site_id>/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{"custom_fields": {"Customer_Auth_Type_Deployment": "2 - DHCP"}}'
```

Only do this when the ENTIRE site (all buildings) has cut over.

### Step 7 — Monitor

For 48 hours after cutover:
- Watch Prometheus: `mikrotik_device_up{site_id="000007"}` — no unexpected drops
- Watch Kea lease count vs expected subscriber count
- Watch kea-sync logs for resolution errors
- Confirm no PPPoE sessions remain for cut-over building in Splynx

## Rollback

If IPoE fails for a building:
1. Remove DHCP relay config from switch (ssh_mcp propose → approve)
2. Subscribers' CPE PPPoE clients will reconnect automatically
3. Do NOT modify Kea host reservations — they are non-destructive

## Notes

- Hardware offload MUST remain OFF during and after cutover until stability is confirmed on 7.21.3
- DHCP unicast renewals carry no Option 82 — host reservations on circuit-id are mandatory
- freeRADIUS continues to run during migration for PPPoE buildings — do not decommission
- Switch `000007.036.RFSW01` had memory OOM warning — verify it was rebooted before including in cutover
