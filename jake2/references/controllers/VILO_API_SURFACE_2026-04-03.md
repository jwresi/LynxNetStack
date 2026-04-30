# Vilo API Surface 2026-04-03

This is the read-only Vilo ISP API surface verified against `https://beta-api.viloliving.com` using the signed client in the old Jake `mcp/vilo_mcp.py`.

## Confirmed

- `GET /isp/v1/access_token`
  - token bootstrap
  - query includes `appkey`, `enc_appsecret`, `timestamp`
- `POST /isp/v1/refresh`
  - refreshes the access token
  - returns `access_token`, `refresh_token`, `expires_in`
- `GET /isp/v1/inventory`
- `POST /isp/v1/inventory`
  - search/filter form of inventory
- `GET /isp/v1/subscribers`
- `POST /isp/v1/subscribers`
  - search/filter form of subscribers
- `GET /isp/v1/networks`
- `POST /isp/v1/networks`
  - search/filter form of networks
- `GET /isp/v1/vilos`
  - device detail by `network_id`
- `POST /isp/v1/vilos`
  - search/sort form for Vilo devices by `network_id`

## Confirmed Missing

- `POST /isp/v1/refresh_token`
  - returned `404`
- `GET /isp/v1/inventory/detail`
  - returned `404`
- `GET /isp/v1/inventory/search`
  - returned `404`
- `GET /isp/v1/device/detail`
  - returned `404`
- `GET /isp/v1/device/stats`
  - returned `404`
- `GET /isp/v1/device/clients`
  - returned `404`
- `GET /isp/v1/dashboard/summary`
  - returned `404`
- `GET /isp/v1/statistics/overview`
  - returned `404`

## Strongly Inferred Present But Unusable So Far

These paths returned `405 Method Not Allowed`, which means the route exists on the beta API, but our guessed method is wrong or additional headers/body shape is required.

- `GET /isp/v1/networks/detail`
- `GET /isp/v1/networks/devices`
- `GET /isp/v1/networks/topology`
- `GET /isp/v1/subscribers/detail`
- `GET /isp/v1/subscribers/networks`
- `GET /isp/v1/subscribers/devices`
- `GET /isp/v1/vilos/detail`

The same endpoints also returned `405` when tried as `POST`, `PUT`, `PATCH`, and `OPTIONS`.

### Important Allow-Header Finding

For every route above, the beta API returned:

- `Allow: DELETE`

That means these paths are very unlikely to be the missing read-only detail endpoints we want. They look more like odd delete-only routes, placeholder handlers, or vendor-side routing artifacts. Jake should not treat them as likely hidden read surfaces just because they returned `405`.

## Implications

- The repo client was already correct to use `/isp/v1/refresh`, not `/isp/v1/refresh_token`.
- `vilos` is a real first-class resource family and should be treated as confirmed API surface, not just an internal helper guess.
- The best practical read surface today is still:
  - inventory
  - subscribers
  - networks
  - vilos
- The `detail` and `topology` families above are `exists-but-suspicious`, not good read-surface candidates.
- The best practical read surface remains:
  - inventory
  - subscribers
  - networks
  - vilos

## Portal-Confirmed Network Detail Surface

The live `isp.viloliving.com` frontend exposes a deeper controller surface on the per-network detail page (`/networkview`) than the signed client currently uses.

Confirmed from the live `chunk-1e264c28.a0458d6b.js` bundle:

- `POST /isp/v1/mesh_info/get`
- `POST /isp/v1/mesh_device_list/get`
- `POST /isp/v1/dhcp_list/get`
- `POST /isp/v1/router/flow_list/get`
- `POST /isp/v1/device/property_list/get`
- `POST /isp/v1/device/property_list/set`
- `POST /isp/v1/router/external_info/set`
- `POST /isp/v1/router/external/delete`
- `POST /isp/v1/auto/action/run`
- `POST /isp/v1/device/upgrade_list/get`
- `POST /isp/v1/device/delete`
- `POST /isp/v1/device/device_info/set`
- `POST /isp/v1/speed/get`
- `POST /isp/v1/router/target_chart/get`
- `POST /isp/v1/exdevice_list/property_list/get`
- `POST /isp/v1/exdevice_list/property_list/set`
- `POST /isp/v1/channel/get`

Additional portal-only read families confirmed from the same bundle set:

- `POST /isp/v1/user_mesh/get_list`
- `POST /isp/v1/access/get`
- `POST /isp/v1/activity_log/get`
- `POST /isp/v1/subscriber_list/get`
- `POST /isp/v1/assign_subscriber_list/get`
- `POST /isp/v1/manager_list/get`
- `POST /isp/v1/user/timezone/get`

Additional portal-only write families confirmed from the same bundle set:

- `POST /isp/v1/mesh_subscriber/set`
- `POST /isp/v1/mesh/move`
- `POST /isp/v1/assign/cancel`
- `POST /isp/v1/manager/set`
- `POST /isp/v1/user_mesh/set`
- `POST /isp/v1/device_list/property_list/set`

## Portal UI Capability Map

The per-network `networkview` page exposes these feature tabs in the live bundle:

- `Usage Report`
- `Guest Wi-Fi`
- `Wi-Fi Settings`
- `Wi-Fi Interference`
- `Restart Vilos`
- `Schedule Regular Restarts`
- `Speed Check`
- `Firmware Upgrade`
- `WAN Settings`
- `LAN Settings`
- `DHCP Reservations`
- `Port Forwarding`
- `Other Settings`
- `Operation Logs`
- `Submit a Firmware Log`

### WAN Settings Tab

The `networkview` page includes a real `WAN Settings` tab.

Confirmed UI labels:

- `DHCP`
- `PPPoE`
- `Static IP Access`

Confirmed property IDs read from `device/property_list/get`:

- `P2100`
  - WAN mode selector
  - `1=DHCP`, `2=PPPoE`, `3=Static IP Access`
- `P2101`
  - DHCP DNS mode
  - `0=Auto Configuration`, `1=Manual Configuration`
- `P2102`
  - `DNS1`
- `P2103`
  - `DNS2`
- `P2104`
  - PPPoE username
- `P2105`
  - PPPoE password
- `P2106`
  - Static IP address
- `P2107`
  - Static subnet mask
- `P2108`
  - Static gateway
- `P2180`
  - LAN/bridge mode state that gates whether PPPoE or Static IP can be used

Confirmed target PID list used by the portal:

- `["P2100","P2101","P2102","P2103","P2104","P2105","P2106","P2107","P2108","P2180"]`

Confirmed request shape used by the portal for WAN reads:

- endpoint:
  - `POST /isp/v1/device/property_list/get`
- body:
  - `data.device_mac=<main_device>`
  - `data.device_model=<device_model>`
  - `data.target_pid_list=[...]`

Confirmed request shape used by the portal for WAN writes:

- endpoint:
  - `POST /isp/v1/device/property_list/set`
- body:
  - `data.device_mac=<main_device>`
  - `data.device_model=<device_model>`
  - `data.property_list=[{pid,pvalue}, ...]`

### LAN Settings Tab

Confirmed LAN property IDs from the same `networkview` bundle:

- `P2180`
  - LAN mode selector
  - includes bridge-mode behavior
- `P2174`
  - LAN IP address
- `P2175`
  - subnet mask
- `P2177`
  - DHCP start IP
- `P2178`
  - DHCP end IP

Confirmed request shape used by the portal for LAN reads:

- endpoint:
  - `POST /isp/v1/device/property_list/get`
- body:
  - `data.device_mac=<main_device>`
  - `data.device_model=<device_model>`
  - `data.target_pid_list=["P2100","P2180","P2174","P2175","P2177","P2178"]`

### Usage / DHCP / Port Forwarding

Confirmed controller read endpoints by feature:

- Usage Report:
  - `POST /isp/v1/router/flow_list/get`
  - body includes `mesh_id`, `begin_ts`, `end_ts`, `query_unit`, and `exdevice_list`
- DHCP Reservations:
  - `POST /isp/v1/dhcp_list/get`
- Port Forwarding:
  - `POST /isp/v1/router/flow_list/get` for read-side flow data
  - `POST /isp/v1/router/external_info/set` for write-side updates
  - `POST /isp/v1/router/external/delete` for deletions

### Credential Handling

- The portal hydrates `P2104` directly into the WAN settings form.
- The portal also reads `P2105`, but runs it through a `key_word` helper before showing it in the form.
- The same `key_word` helper is used elsewhere in the portal for Wi-Fi passwords, so `P2105` is not simply omitted from reads; it is fetched and then de-obfuscated client-side through another controller call/helper.

### Why This Matters

- The live controller does have a readable WAN-settings surface.
- The currently implemented signed Vilo client in `mcp/vilo_mcp.py` does not expose that surface yet.
- The actual unit identifier may still be recoverable from PPPoE credentials or other WAN fields on the controller detail page, even though `subscriber_id` and `user_email` are blank in the simpler `networks` response.

## Portal Auth Chain

The live ISP portal does not use the same simple auth path as the earlier read-only `mcp/vilo_mcp.py` client.

Frontend bundles confirm this split:

## Repo-Grounded Hidden Read Contracts

The private repo `ResiBridge/Vilo_API` adds two important grounded sources:

- `vilo_api.py`
  - already knew about hidden write families like `device/property_list/set` and `auto/action/run`
  - already knew that PPPoE writes use:
    - `P2100=2`
    - `P2104=<username>`
    - `P2105=<password>`
- `beta-new-isp.viloliving.com.har`
  - contains real successful browser request/response pairs for the hidden controller

The HAR proves exact successful read payloads for:

- `POST /isp/v1/user_mesh/get_list`
- `POST /isp/v1/mesh_info/get`
- `POST /isp/v1/device/device_list/get`
- `POST /isp/v1/device/property_list/get`

### Exact Successful Read Examples From HAR

- `mesh_info/get`
  - request `data={"main_device":"E8DA00150A3B","type":1}`
  - response includes:
    - `nick_name`
    - `firmware_ver`
    - `ip=192.168.58.1`
    - `router_online`
    - `sub_router_online`
    - `device_online_offline`
    - `exdevice_count`

- `device/device_list/get`
  - request `data={"filter_group":[],"page_size":25,"page_index":1,"order":"desc"}`
  - response `data.device_list[]` includes:
    - `device_mac`
    - `device_sn`
    - `device_model`
    - `status`
    - `subscriber`
    - `user`
    - `notes`
    - `create_time`
    - `update_time`
  - `notes` is an important hidden label source and contains real unit strings like:
    - `NYCHA1578SterlingPl3E`
    - `NYCHA1578SterlingPl3D`
    - `NYCHA1578SterlingPl3C`

- `device/property_list/get`
  - request for WAN settings:
    - `data.device_mac=<main_device>`
    - `data.device_model=<device_model>`
    - `data.target_pid_list=["P2100","P2101","P2102","P2103","P2104","P2105","P2106","P2107","P2108","P2180"]`
  - response `data.property_list[]` includes:
    - `P2104`
      - PPPoE username
      - real examples from HAR:
        - `NYCHA2058UnionSt6B`
        - `NYCHA1578SterlingPl3E`

### Operational Implication

For NYCHA unit labeling, the best Vilo controller sources are:

1. `device/property_list/get -> P2104`
2. `device/device_list/get -> notes`
3. public `network_name`
4. public `subscriber_id` / `user_email`

The downloaded HAR capture referenced during the old-Jake audit was empty (`entries=[]`) and did not provide any additional live route evidence.

- `https://dev-user-api.kivolabs.com`
  - HMAC-signed `iot_web` requests
  - used for account policy and rights retrieval
- `https://usercenter-api.kivolabs.com`
  - plain JSON login/token requests
  - used to mint the token the portal stores as `access_token_usercenter`
- `https://isp-api.viloliving.com`
  - HMAC-signed `vilo_isp` requests
  - used for hidden controller reads and writes from `/networkview`

Grounded login sequence from the login chunk:

1. `POST https://usercenter-api.kivolabs.com/api/token/get`
   - body data:
     - `account_name`
     - `account_type=2`
     - `password=<triple_md5(user_password)>`
   - extra request fields:
     - `app_id=bfa842fc4d04a20508dc7ec61574`
     - `sc=5be027c460364fbcb6e54c762dd325ac`
     - `language=en`
     - `sv=6e6fcfe8cfdf4622beb45b659491a6bd`
2. Response returns:
   - `user_id`
   - `access_token`
   - this token is stored by the portal as `access_token_usercenter`
3. `POST https://dev-user-api.kivolabs.com/v1/account/get`
   - body data:
     - `platform_id`
     - `user_id`
     - `account_name`
     - `account_type=2`
4. Response returns:
   - `company_id`
   - `super_state`
   - ordinary `access_token`
   - `time_zone`
5. `POST https://dev-user-api.kivolabs.com/v1/login/get_user_right`
   - used for menus/rights
6. Hidden controller calls then use:
   - base URL: `https://isp-api.viloliving.com`
   - `H-AccessToken=<access_token_usercenter>`
   - `H-AppKey=5be027c460364fbcb6e54c762dd325ac`
   - `H-Signature=HMAC_SHA256(appkey + timestamp + JSON.stringify(full_request_body), secret)`
   - `secret=7c4b3e35c94145d89c9374dcdfe9c40f`
   - `app_name=vilo_isp`
   - `H-AccessPath=<window.location.pathname>`

Confirmed full request wrapper from the bundle:

- root fields added by the portal client before each `vilo_isp` request:
  - `timestamp`
  - `app_name="vilo_isp"`
  - `app_version="1.0"`
  - `os_name="5.0"`
  - `os_version="5.0"`
  - `request_id=<uuid-without-dashes>`
  - `data=<endpoint-specific-body>`

## Portal Rights Model

Chrome local storage preserved a prior portal rights blob for an operator account. The cached role set proves the account has at least these portal capabilities when logged in:

- `networkview:list`
- `networkview:run_speed`
- `networkview:run_speed_history`
- `vilos:view`
- `vilos:update_note`
- `vilos:del`
- `vilos:remote_installation`
- `networks:view`
- `networks:del`
- `networks:internetAccess`
- `customers:edit`
- `accounts:add`
- `accounts:active`
- `accounts:deactivate`
- `accounts:del`
- `accounts:set_role`
- `access_levels:add`
- `access_levels:edit`
- `access_levels:del`

Current live auth result:

- A previously available credential pair was tested against the grounded `usercenter-api.kivolabs.com/api/token/get` flow.
- Result:
  - HTTP `200`
  - application `code="2000"`
  - message `username or password is error`

So:

- the auth flow is confirmed
- the currently available credentials are not valid for the Vilo ISP portal

## Current Crawl Boundary

- A cached Chrome `kivoispmsg` blob exists for `https://beta-isp.viloliving.com`, but the stored `access_token_usercenter` is stale.
- Replaying hidden controller reads with that stale token now returns:
  - `code="2001"` / `AccessTokenError`
- So the remaining blocker for a full live hidden-endpoint crawl is a fresh portal session token, not uncertainty about hostnames, signing, or route names.

## Beta-New Portal Variant

The newer beta portal at `https://beta-new-isp.viloliving.com` is a distinct frontend build and should be treated as the preferred beta portal target.

Confirmed from the live `app.942c9d9e.js` bundle:

- frontend host:
  - `https://beta-new-isp.viloliving.com`
- beta controller host:
  - `https://beta-isp-api.viloliving.com`
- beta account host:
  - `https://beta-dev-user-api.kivolabs.com`
- token host:
  - `https://usercenter-api.kivolabs.com`

Additional beta-new controller families confirmed from the bundle:

- `POST /isp/v1/device/device_list/get`
- `POST /isp/v1/network_mesh_list/get`
- `POST /isp/v1/network_info/get`
- `POST /isp/v1/capacity/get`
- `POST /isp/v1/flowdata/get`
- `POST /isp/v1/message/get`
- `POST /isp/v1/setting_list/get`
- `POST /isp/v1/last_install/get`
- `POST /isp/v1/operate_list/get`
- `POST /isp/v1/attachment_url/get`
- `POST /isp/v1/auto_binding/get`
- `POST /isp/v1/auto_binding/set`
- `POST /isp/v1/device/distribute_user/set`
- `POST /isp/v1/user/user_list/get`
- `POST /isp/v1/user/user_info/add`
- `POST /isp/v1/user/user_info/set`
- `POST /isp/v1/user/user_info/delete`
- `POST /isp/v1/networks/manager`
- `POST /isp/v1/auto/action_list/run`
- `POST /isp/v1/inventory/statistic`
- `POST /isp/v1/network/statistic`
- `POST /isp/v1/mesh_map/statistic`
- `POST /isp/v1/upgrade_status/statistic`
- `POST /isp/v1/vilo/ststistic`

## Beta-New Request Wrapper

The newer beta portal uses the same app key and secret as the other portal builds, but the wrapper differs in one important way:

- `app_name="iot_web"`

Confirmed beta-new controller wrapper:

- `H-AppKey=5be027c460364fbcb6e54c762dd325ac`
- `H-SignatureMethod=1`
- `H-AccessPath=<window.location.pathname>`
- `Cache-Control=no-cache`
- `H-Signature = HMAC_SHA256(appkey + timestamp + JSON.stringify(full_request_body), secret)`
- secret:
  - `7c4b3e35c94145d89c9374dcdfe9c40f`
- root request body fields:
  - `timestamp`
  - `app_name="iot_web"`
  - `app_version="1.0"`
  - `os_name="5.0"`
  - `os_version="5.0"`
  - `request_id`
  - `data`

## Live Read Boundary On Beta-New

Using a fresher cached Chrome session blob from `isp.viloliving.com`:

- `POST https://beta-isp-api.viloliving.com/isp/v1/setting_list/get`
  - returned `code="1"` and real setting data

But protected controller reads still returned `code="2001" / AccessTokenError`:

- `POST /isp/v1/network_mesh_list/get`
- `POST /isp/v1/mesh_info/get`
- `POST /isp/v1/device/device_list/get`
- `POST /isp/v1/device/property_list/get`
- `POST /isp/v1/user/timezone/get`

Implication:

- hidden route families and request shapes are grounded
- `setting_list/get` is weakly readable with cached session state
- the protected per-network and per-device surfaces still require a fresh live portal session

## Exact Protected Read Shapes

The newer beta bundle gives exact request shapes for several protected controller reads:

- WAN settings read:
  - endpoint:
    - `POST /isp/v1/device/property_list/get`
  - body:
    - `data.device_mac=<main_device>`
    - `data.device_model=<device_model>`
    - `data.target_pid_list=["P2100","P2101","P2102","P2103","P2104","P2105","P2106","P2107","P2108","P2180"]`

- LAN settings read:
  - endpoint:
    - `POST /isp/v1/device/property_list/get`
  - body:
    - `data.device_mac=<main_device>`
    - `data.device_model=<device_model>`
    - `data.target_pid_list=["P2100","P2180","P2174","P2175","P2177","P2178"]`

- Usage report property read:
  - endpoint:
    - `POST /isp/v1/device/property_list/get`
  - body:
    - `data.device_mac=<main_device>`
    - `data.device_model=<device_model>`
    - `data.target_pid_list=["P2150","P2180","P2192"]`

- Scheduled speed-check property read:
  - endpoint:
    - `POST /isp/v1/device/property_list/get`
  - body:
    - `data.device_mac=<main_device>`
    - `data.device_model=<device_model>`
    - `data.target_pid_list=["P2187"]`

- Usage report flow read:
  - endpoint:
    - `POST /isp/v1/router/flow_list/get`
  - body:
    - `data.begin_ts=<ms>`
    - `data.end_ts=<ms>`
    - `data.query_unit=1`
    - `data.mesh_id=<mesh_id>`
    - `data.exdevice_list=[]`
