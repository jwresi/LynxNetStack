# Vilo ISP API Surface — Updated 2026-04-08

Supersedes VILO_API_SURFACE_2026-04-03.md. All endpoints confirmed live.

## Two Separate API Clients

### Client 1: ISP Read API (vilo_mcp.py)
- Base URL: https://beta-api.viloliving.com
- Token: GET /isp/v1/access_token?appkey=X&enc_appsecret=triple_md5(secret+ts)&timestamp=ts
- Credentials: VILO_APPKEY / VILO_APPSECRET in .env
- Scope: read-only inventory, networks, subscribers, vilos
- Cannot access hidden write endpoints

### Client 2: Portal API (newly confirmed 2026-04-08)
- Base URL: https://beta-isp-api.viloliving.com
- App key: store in `VILO_PORTAL_APP_KEY`
- App secret: store in `VILO_PORTAL_APP_SECRET`
- Token: access_token_usercenter from browser localStorage kivoispmsg (base64 JSON blob)
- Full read/write access including reboot, factory reset, delete, property set

## Portal Signing — CONFIRMED EXACT (from webpack module 785f)

Body field order is critical (JSON.stringify preserves insertion order):
  {"data": {...}, "timestamp": 1234567890000, "app_name": "vilo_isp",
   "app_version": "1.0", "os_name": "5.0", "os_version": "5.0", "request_id": "uuid-no-dashes"}

Signing: HMAC_SHA256(APP_KEY + str(timestamp_ms) + JSON.stringify(full_body), APP_SECRET)

Headers: H-AppKey, H-Signature, H-SignatureMethod=1, H-AccessToken, H-AccessPath=/networkview,
         Cache-Control=no-cache, Origin=https://beta-isp.viloliving.com

## Getting a Fresh Token
1. Log into https://beta-isp.viloliving.com with an authorized operator account.
2. DevTools console: copy(localStorage.getItem('kivoispmsg'))
3. Parse JSON, base64-decode access_token_usercenter field
Token expires after several hours. Expired = code=2001 AccessTokenError.

## Confirmed Working Endpoints

POST /isp/v1/mesh_info/get
  data: {main_device: "E8DA001503B1", type: 1}
  returns: nick_name, firmware_ver, ip, router_online, sub_router_online,
           device_online_offline, exdevice_count, device_model

POST /isp/v1/device/device_list/get
  data: {filter_group: [], page_size: 100, page_index: 1, order: "desc"}
  returns: device_list[] — device_mac, device_sn, device_model, status,
           notes (NYCHA unit label), group_id, split_device
  Total inventory: 1225 devices as of 2026-04-08. Paginated.

POST /isp/v1/device/property_list/get
  data: {device_mac, device_model, target_pid_list: [...]}
  PIDs: P2100=WAN mode (1=DHCP,2=PPPoE,3=Static), P2104=PPPoE user, P2105=PPPoE pass,
        P2174=LAN IP, P2175=subnet mask, P2180=bridge mode, P2187=schedule restart

POST /isp/v1/auto/action/run  — CONFIRMED WORKING
  Reboot: {provider_key:"KIVO_MeshRouter", action_key:"reboot_router_list",
           instance_id:"E8DA001503B1", action_params:{mac_list:["E8:DA:00:15:03:B1"]},
           custom_string:""}
  Schedule reboot: action_key="schedule_reboot_router",
                   action_params={crontab:"MM|HH|SMTWTFS", isopen:1}

POST /isp/v1/device/property_list/set
  data: {device_mac, device_model, property_list:[{pid,pvalue},...]}
  Use to set PPPoE: P2100=2, P2104=username, P2105=password

POST /isp/v1/device/delete       — confirmed in bundle, shape TBD
POST /isp/v1/mesh/move            — move device between networks, shape TBD
POST /isp/v1/device/device_info/set  — update notes/labels
POST /isp/v1/device_list/property_list/set  — bulk property set
POST /isp/v1/mesh_device_list/get  — devices in a mesh (returns empty for single units)
POST /isp/v1/dhcp_list/get        — DHCP reservations
POST /isp/v1/router/external_info/set  — port forwarding
POST /isp/v1/router/external/delete   — delete port forward rule

## Device Models
- KIVO_MeshRouter: primary mesh unit (E8:DA:00:15:xx:xx MACs)
- VLWF01: 1-pack standalone/satellite (E8:DA:00:14:xx:xx MACs)

## Key Operational Findings

### Notes Field = NYCHA Unit Label
device/device_list/get notes field contains unit label e.g. "NYCHA1588SterlingPl1A"
This is the most reliable unit identifier in the Vilo system.

### PPPoE Username Pattern
NYCHA{AddressNoSpaces}{Unit} e.g.:
  NYCHA1588SterlingPl1A, NYCHA2058UnionSt6B, NYCHA1578SterlingPl3E

### LAN IP
Always 192.168.58.1 per unit (each Vilo is an isolated router serving its apartment subnet).
Not reachable from building network — faces apartment LAN side only.

### split_device Field
"No Mesh" = standalone network in portal view.
Note: units can still firmware-level mesh wirelessly regardless of portal setting.

### 1588 Sterling Pl Root Cause (confirmed 2026-04-08)
Units 01A/B/C/D/E/03B are correctly configured (PPPoE, correct credentials).
They are NOT portal satellites of Vilo_03b1.
They auto-join Vilo_03b1 mesh at firmware level because primary is physically nearby
(1629 Park Pl, broadcasting mesh SSID within wireless range of 1588 Sterling).
Fix: physically move/reset Vilo_03b1 primary (E8:DA:00:15:03:B1) to correct address
     672 Ralph Ave Unit 02A (per NYCHA pre-install CSV).

## Portal Account
URL: https://beta-isp.viloliving.com
Login: use an authorized operator account from your private credential store
Roles: vilos:del, vilos:view, vilos:update_note, vilos:remote_installation,
       networks:del, networks:view, networks:internetAccess,
       networkview:list, networkview:run_speed, networkview:run_speed_history,
       accounts:add/del/active/deactivate/set_role, customers:edit,
       access_levels:add/edit/del

## Bundle Reference (beta-isp.viloliving.com)
App bundle: /static/js/app.19d4367b.js (669KB)
Signing logic: webpack module 785f
Network view actions (reboot, delete, property set): webpack module 71c2
Mesh/user actions: webpack module f1d3
Restart UI component: webpack module bf4d
