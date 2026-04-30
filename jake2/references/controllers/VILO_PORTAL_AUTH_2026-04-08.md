# Vilo Portal Auth — Quick Reference 2026-04-08

## Credentials
- Portal: https://beta-isp.viloliving.com
- Login: use your current operator credential from a private env or password manager
- App key: store in `VILO_PORTAL_APP_KEY`
- App secret: store in `VILO_PORTAL_APP_SECRET`
- API base: https://beta-isp-api.viloliving.com

## Getting a Fresh Token
Log into portal, then in DevTools console:
  copy(localStorage.getItem('kivoispmsg'))
Parse the JSON, base64-decode the access_token_usercenter field.

## Python Client Template

```python
import hashlib, hmac as hmac_lib, json, urllib.request, uuid, time

import os

APP_KEY = os.environ['VILO_PORTAL_APP_KEY']
APP_SECRET = os.environ['VILO_PORTAL_APP_SECRET']
ISP_BASE = os.environ.get('VILO_PORTAL_API_BASE', 'https://beta-isp-api.viloliving.com')
ACCESS_TOKEN = os.environ['VILO_PORTAL_TOKEN']

def isp_post(path, data_body):
    ts = int(time.time() * 1000)
    rid = uuid.uuid4().hex.replace('-','')
    body = {'data': data_body}
    body['timestamp'] = ts
    body['app_name'] = 'vilo_isp'
    body['app_version'] = '1.0'
    body['os_name'] = '5.0'
    body['os_version'] = '5.0'
    body['request_id'] = rid
    body_str = json.dumps(body, separators=(',',':'))
    sig = hmac_lib.new(APP_SECRET.encode(),
        (APP_KEY + str(ts) + body_str).encode(),
        hashlib.sha256).hexdigest()
    headers = {
        'Content-Type': 'application/json',
        'H-AppKey': APP_KEY,
        'H-Signature': sig,
        'H-SignatureMethod': '1',
        'H-AccessToken': ACCESS_TOKEN,
        'H-AccessPath': '/networkview',
        'Cache-Control': 'no-cache',
        'Origin': 'https://beta-isp.viloliving.com',
        'Referer': 'https://beta-isp.viloliving.com/',
    }
    req = urllib.request.Request(f"{ISP_BASE}{path}",
        data=body_str.encode(), headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())
```

## Common Operations

### Check network status
isp_post('/isp/v1/mesh_info/get', {'main_device': 'E8DA001503B1', 'type': 1})

### Find device by MAC
isp_post('/isp/v1/device/device_list/get',
    {'filter_group': [{'key': 'device_mac', 'value': 'E8:DA:00:14:E6:35'}],
     'page_size': 5, 'page_index': 1, 'order': 'desc'})

### Get WAN config / PPPoE credentials
isp_post('/isp/v1/device/property_list/get', {
    'device_mac': 'E8DA0014E635',
    'device_model': 'VLWF01',
    'target_pid_list': ['P2100','P2104','P2105','P2174','P2180']
})

### Reboot a network
isp_post('/isp/v1/auto/action/run', {
    'provider_key': 'KIVO_MeshRouter',
    'action_key': 'reboot_router_list',
    'instance_id': 'E8DA001503B1',
    'action_params': {'mac_list': ['E8:DA:00:15:03:B1']},
    'custom_string': ''
})

### Set PPPoE credentials
isp_post('/isp/v1/device/property_list/set', {
    'device_mac': 'E8DA0014E635',
    'device_model': 'VLWF01',
    'property_list': [
        {'pid': 'P2100', 'pvalue': '2'},
        {'pid': 'P2104', 'pvalue': 'NYCHA1588SterlingPl1A'},
        {'pid': 'P2105', 'pvalue': '<password>'},
    ]
})
