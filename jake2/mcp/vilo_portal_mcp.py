"""
Vilo ISP Portal API Client — 2026-06-05
Confirmed working against https://beta-isp-api.viloliving.com

Separate from vilo_mcp.py (read-only ISP client).
This client uses portal-level auth with full read/write access.

Auth: fully automated — calls vilo_portal_login() which authenticates
      against usercenter-api.kivolabs.com using stored credentials.
      Tokens are cached and auto-refreshed. No browser session needed.

Credentials (embedded — do not rotate without updating here):
  APP_KEY:    5be027c460364fbcb6e54c762dd325ac
  APP_SECRET: 7c4b3e35c94145d89c9374dcdfe9c40f
  account:    jw@resibridge.com
  pwd_hash:   bed766e7d2f7a5a9b11cac37758bda3b  (pre-hashed, not plain MD5)
"""

from __future__ import annotations
import base64, hashlib, hmac as hmac_lib, json, os, time, urllib.request, uuid
from typing import Any

# Embedded credentials — discovered 2026-06-05 via browser capture
APP_KEY    = os.environ.get("VILO_PORTAL_APP_KEY",    "5be027c460364fbcb6e54c762dd325ac")
APP_SECRET = os.environ.get("VILO_PORTAL_APP_SECRET", "7c4b3e35c94145d89c9374dcdfe9c40f")
ISP_BASE   = os.environ.get("VILO_PORTAL_API_BASE",   "https://beta-isp-api.viloliving.com")
UC_BASE    = "https://usercenter-api.kivolabs.com"

_ACCOUNT   = os.environ.get("VILO_PORTAL_ACCOUNT",  "jw@resibridge.com")
_PWD_HASH  = os.environ.get("VILO_PORTAL_PWD_HASH", "bed766e7d2f7a5a9b11cac37758bda3b")
_APP_ID    = "bfa842fc4d04a20508dc7ec61574"
_SV        = "6e6fcfe8cfdf4622beb45b659491a6bd"

# Module-level token cache
_cached_token: str = ""
_cached_refresh: str = ""
_token_expires_at: float = 0.0


def vilo_portal_login() -> str:
    """
    Authenticate against usercenter-api.kivolabs.com and return a fresh
    access_token_usercenter. Caches the result; auto-refreshes on expiry.
    """
    global _cached_token, _cached_refresh, _token_expires_at

    # Return cached token if still valid (with 5-min buffer)
    if _cached_token and time.time() < _token_expires_at - 300:
        return _cached_token

    # Try refresh token first
    if _cached_refresh:
        token = _try_refresh(_cached_refresh)
        if token:
            return token

    # Full login
    ts = int(time.time() * 1000)
    body = {
        "data": {
            "account_name": _ACCOUNT,
            "account_type": 2,
            "password": _PWD_HASH,
        },
        "timestamp": ts,
        "app_id": _APP_ID,
        "sc": APP_KEY,
        "language": "en",
        "sv": _SV,
    }
    body_str = json.dumps(body, separators=(',', ':'))
    sig = hmac_lib.new(APP_SECRET.encode(), (APP_KEY + str(ts) + body_str).encode(), hashlib.sha256).hexdigest()
    headers = {
        'Content-Type': 'application/json',
        'H-AppKey': APP_KEY, 'H-Signature': sig, 'H-SignatureMethod': '1',
        'H-AccessToken': '', 'H-AccessPath': '/login',
        'Origin': 'https://beta-isp.viloliving.com',
        'Referer': 'https://beta-isp.viloliving.com/',
    }
    req = urllib.request.Request(f"{UC_BASE}/api/token/get",
        data=body_str.encode(), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
    except Exception as e:
        raise RuntimeError(f"Vilo login failed: {e}")

    if str(resp.get('code')) != '1':
        raise RuntimeError(f"Vilo login error: {resp.get('message')} (code={resp.get('code')})")

    data = resp.get('data', {})
    _cached_token   = data.get('access_token', '')
    _cached_refresh = data.get('refresh_token', '')
    # Tokens appear to be valid ~24h; cache for 23h
    _token_expires_at = time.time() + 23 * 3600
    return _cached_token


def _try_refresh(refresh_token: str) -> str:
    """Attempt to get a new access token using the refresh token."""
    global _cached_token, _cached_refresh, _token_expires_at
    ts = int(time.time() * 1000)
    body = {
        "data": {"refresh_token": refresh_token},
        "timestamp": ts,
        "app_id": _APP_ID,
        "sc": APP_KEY,
        "language": "en",
    }
    body_str = json.dumps(body, separators=(',', ':'))
    sig = hmac_lib.new(APP_SECRET.encode(), (APP_KEY + str(ts) + body_str).encode(), hashlib.sha256).hexdigest()
    headers = {
        'Content-Type': 'application/json',
        'H-AppKey': APP_KEY, 'H-Signature': sig, 'H-SignatureMethod': '1',
        'H-AccessToken': '', 'H-AccessPath': '/login',
        'Origin': 'https://beta-isp.viloliving.com',
        'Referer': 'https://beta-isp.viloliving.com/',
    }
    try:
        req = urllib.request.Request(f"{UC_BASE}/api/token/refresh",
            data=body_str.encode(), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
        if str(resp.get('code')) == '1':
            data = resp.get('data', {})
            _cached_token   = data.get('access_token', '')
            _cached_refresh = data.get('refresh_token', _cached_refresh)
            _token_expires_at = time.time() + 23 * 3600
            return _cached_token
    except Exception:
        pass
    return ''


def decode_kivoispmsg(blob: str) -> dict[str, str]:
    """Decode the kivoispmsg localStorage blob from the Vilo portal."""
    data = json.loads(blob)
    return {k: base64.b64decode(v).decode('utf-8', errors='replace')
            for k, v in data.items()}


class ViloPortalClient:
    """
    Portal-level Vilo ISP API client. Auth is fully automated —
    no browser session or manual token extraction required.
    """

    def __init__(self, access_token: str | None = None) -> None:
        # If an explicit token is passed (e.g. from env), use it.
        # Otherwise auto-login.
        self._explicit_token = access_token or os.environ.get('VILO_PORTAL_TOKEN', '')

    @property
    def access_token(self) -> str:
        if self._explicit_token:
            return self._explicit_token
        return vilo_portal_login()

    def configured(self) -> bool:
        return bool(APP_KEY and APP_SECRET)

    def post(self, path: str, data_body: dict[str, Any]) -> dict[str, Any]:
        if not self.configured():
            raise RuntimeError(
                'Vilo portal client requires VILO_PORTAL_TOKEN, '
                'VILO_PORTAL_APP_KEY, and VILO_PORTAL_APP_SECRET in the environment.'
            )
        ts = int(time.time() * 1000)
        rid = uuid.uuid4().hex.replace('-', '')
        body: dict[str, Any] = {'data': data_body}
        body['timestamp'] = ts
        body['app_name'] = 'vilo_isp'
        body['app_version'] = '1.0'
        body['os_name'] = '5.0'
        body['os_version'] = '5.0'
        body['request_id'] = rid
        body_str = json.dumps(body, separators=(',', ':'))
        sig = hmac_lib.new(
            APP_SECRET.encode(),
            (APP_KEY + str(ts) + body_str).encode(),
            hashlib.sha256
        ).hexdigest()
        headers = {
            'Content-Type': 'application/json',
            'H-AppKey': APP_KEY,
            'H-Signature': sig,
            'H-SignatureMethod': '1',
            'H-AccessToken': self.access_token,
            'H-AccessPath': '/networkview',
            'Cache-Control': 'no-cache',
            'Origin': 'https://beta-isp.viloliving.com',
            'Referer': 'https://beta-isp.viloliving.com/',
        }
        req = urllib.request.Request(
            f"{ISP_BASE}{path}",
            data=body_str.encode(),
            headers=headers,
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return {'_http': e.code, '_body': e.read().decode()[:300]}

    # ------------------------------------------------------------------ #
    # Read endpoints
    # ------------------------------------------------------------------ #

    def mesh_info(self, main_device: str) -> dict[str, Any]:
        """Get mesh status, firmware, online state for a network."""
        mac = main_device.replace(':', '').upper()
        return self.post('/isp/v1/mesh_info/get', {'main_device': mac, 'type': 1})

    def device_list(self, page: int = 1, page_size: int = 100,
                    filter_group: list | None = None) -> dict[str, Any]:
        """List devices. filter_group e.g. [{'key':'device_mac','value':'E8:DA:...'}]"""
        return self.post('/isp/v1/device/device_list/get', {
            'filter_group': filter_group or [],
            'page_size': page_size,
            'page_index': page,
            'order': 'desc',
        })

    def all_devices(self) -> list[dict[str, Any]]:
        """Fetch all devices across all pages."""
        devices = []
        page = 1
        while True:
            r = self.device_list(page=page)
            if r.get('code') not in ('1', 1):
                break
            batch = (r.get('data') or {}).get('device_list') or []
            if not batch:
                break
            devices.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return devices

    def property_list(self, device_mac: str, device_model: str,
                      pids: list[str] | None = None) -> dict[str, Any]:
        """Get device properties (WAN mode, PPPoE creds, LAN IP etc)."""
        mac = device_mac.replace(':', '').upper()
        return self.post('/isp/v1/device/property_list/get', {
            'device_mac': mac,
            'device_model': device_model,
            'target_pid_list': pids or ['P2100', 'P2104', 'P2105', 'P2174', 'P2180'],
        })

    def get_wan_config(self, device_mac: str, device_model: str = 'VLWF01') -> dict[str, str]:
        """Return dict of PID->value for WAN/LAN config."""
        r = self.property_list(device_mac, device_model,
                               ['P2100', 'P2101', 'P2102', 'P2103',
                                'P2104', 'P2105', 'P2174', 'P2175', 'P2180'])
        props = (r.get('data') or {}).get('property_list') or []
        return {p['pid']: p['value'] for p in props}

    # ------------------------------------------------------------------ #
    # Write endpoints
    # ------------------------------------------------------------------ #

    def reboot(self, main_device: str,
               mac_list: list[str] | None = None,
               device_model: str = 'KIVO_MeshRouter') -> dict[str, Any]:
        """Reboot a device or list of devices in a network."""
        mac = main_device.replace(':', '').upper()
        if mac_list is None:
            fmt = ':'.join(mac[i:i+2] for i in range(0, 12, 2))
            mac_list = [fmt]
        return self.post('/isp/v1/auto/action/run', {
            'provider_key': device_model,
            'action_key': 'reboot_router_list',
            'instance_id': mac,
            'action_params': {'mac_list': mac_list},
            'custom_string': '',
        })

    def get_device_model(self, device_mac: str) -> str:
        """Return the live device_model string (e.g. 'KIVO_MeshRouter') from mesh_info."""
        r = self.mesh_info(device_mac)
        devices = (r.get('data') or {}).get('colume_feature_list') or []
        if devices:
            return devices[0].get('device_model', 'KIVO_MeshRouter')
        return 'KIVO_MeshRouter'

    def set_properties(self, device_mac: str, device_model: str,
                       properties: dict[str, str]) -> dict[str, Any]:
        """Set device properties. properties = {pid: pvalue}"""
        mac = device_mac.replace(':', '').upper()
        return self.post('/isp/v1/device/property_list/set', {
            'device_mac': mac,
            'device_model': device_model,
            'property_list': [{'pid': k, 'pvalue': v} for k, v in properties.items()],
        })

    def set_pppoe(self, device_mac: str, username: str, password: str,
                  device_model: str = 'VLWF01') -> dict[str, Any]:
        """Set PPPoE credentials on a device."""
        return self.set_properties(device_mac, device_model, {
            'P2100': '2',
            'P2104': username,
            'P2105': password,
        })

    def delete_device(self, device_mac: str) -> dict[str, Any]:
        """Remove a device from ISP inventory."""
        mac = device_mac.replace(':', '').upper()
        return self.post('/isp/v1/device/delete', {'device_mac': mac})

    def update_note(self, device_mac: str, note: str) -> dict[str, Any]:
        """Update the notes/label field on a device."""
        mac = device_mac.replace(':', '').upper()
        return self.post('/isp/v1/device/device_info/set', {
            'device_mac': mac,
            'notes': note,
        })


# ------------------------------------------------------------------ #
# CLI smoke test
# ------------------------------------------------------------------ #
if __name__ == '__main__':
    import sys
    print("Authenticating via usercenter-api.kivolabs.com...")
    token = vilo_portal_login()
    print(f"Token: {token[:30]}...")
    client = ViloPortalClient()
    mac = sys.argv[1] if len(sys.argv) > 1 else 'E8DA001503B1'
    r = client.mesh_info(mac)
    print(f"mesh_info {mac}: code={r.get('code')}")
    devs = (r.get('data') or {}).get('colume_feature_list') or []
    for d in devs:
        print(f"  {d.get('nick_name')} online={d.get('router_online')} fw={d.get('firmware_ver')}")
