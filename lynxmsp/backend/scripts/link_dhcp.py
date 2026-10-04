#!/usr/bin/env python3
"""
Link DHCP/RADIUS customers to their switch ports via Splynx live sessions.

Chain: Splynx customers-online (customer_id + MAC) → bridge-host table → switch:ETH{N} → NetBox

Complements link_network.py which covers PPP-based customers via RouterOS sessions.
This script covers DHCP/RADIUS customers (Bulk, Cleveland, Entertainment, Essex etc.)
who show up in Splynx RADIUS sessions but not in RouterOS PPP active tables.

Run inside the backend container:
  docker exec lynxmsp-backend python3 /app/scripts/link_dhcp.py
"""
import sys, os, time, sqlite3, json, re, hmac, hashlib, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_PATH  = '/app/data/lynxcrm.db'
ROSCTL   = 'http://172.27.226.246:3200'
NETBOX   = 'http://172.27.48.233:8001'
NB_TOKEN = '8fd77834b1412f49a09e768be1b379f5416f33c3'
ROS_USER = 'jonathan'
ROS_PASS = 'F7pdn*AQ0Uu4S#t'
SPLYNX   = 'https://crm.resibridge.com'
SP_KEY   = 'bd793c726617bee375996ccbb1c8d092'
SP_SECRET = '9d4124dedfd3cb7ce75aecc70f432d7e'

# ── Splynx auth ──────────────────────────────────────────────────────────────

_sp_token = [None, 0]

def _sp_auth():
    nonce = int(time.time())
    msg   = f'{nonce}{SP_KEY}'
    sig   = hmac.new(SP_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest().upper()
    body  = json.dumps({'auth_type': 'api_key', 'key': SP_KEY, 'signature': sig, 'nonce': nonce}).encode()
    req   = urllib.request.Request(f'{SPLYNX}/api/2.0/admin/auth/tokens', data=body,
                headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=15) as r:
        _sp_token[0] = json.loads(r.read())['access_token']
        _sp_token[1] = time.time()

def _sp_get(path, params=None):
    if not _sp_token[0] or time.time() - _sp_token[1] > 240:
        _sp_auth()
    url = f'{SPLYNX}/api/2.0/{path.lstrip("/")}'
    if params:
        url += '?' + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={'Authorization': f'Splynx-EA (access_token={_sp_token[0]})'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

# ── rosctl auth ──────────────────────────────────────────────────────────────

_ros_token = [None]

def _ros_auth():
    body = json.dumps({'username': ROS_USER, 'password': ROS_PASS}).encode()
    req = urllib.request.Request(f'{ROSCTL}/api/v1/auth/login', data=body,
          headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=10) as r:
        _ros_token[0] = json.loads(r.read())['access_token']

def _ros_get(path, params=None):
    if not _ros_token[0]:
        _ros_auth()
    url = f'{ROSCTL}/api/v1/{path.lstrip("/")}'
    if params:
        url += '?' + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {_ros_token[0]}'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def _ros_command(device_id, command):
    if not _ros_token[0]:
        _ros_auth()
    body = json.dumps({'command': command}).encode()
    req = urllib.request.Request(
        f'{ROSCTL}/api/v1/devices/{device_id}/command', data=body,
        headers={'Authorization': f'Bearer {_ros_token[0]}',
                 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())

# ── NetBox helper ─────────────────────────────────────────────────────────────

def _nb_get(path, params=None):
    url = f'{NETBOX}/api/{path.lstrip("/")}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': f'Token {NB_TOKEN}',
                                               'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

# ── Port name conversion ──────────────────────────────────────────────────────

def ros_port_to_eth(port_name):
    m = re.match(r'ether(\d+)$', port_name, re.I)
    if m:
        return f'ETH{m.group(1)}'
    m = re.match(r'sfp-sfpplus(\d+)$', port_name, re.I)
    if m:
        return f'SFP+{m.group(1)}'
    return None

def normalize_mac(mac: str) -> str:
    """Normalize any MAC format to colon-separated uppercase: AA:BB:CC:DD:EE:FF"""
    s = mac.replace(':', '').replace('-', '').replace('.', '').upper()
    if len(s) != 12:
        return mac.upper()
    return ':'.join(s[i:i+2] for i in range(0, 12, 2))


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Migrate: ensure columns exist ────────────────────────────────────────
    existing = {r[1] for r in cur.execute('PRAGMA table_info(customers)').fetchall()}
    for col, defn in [
        ('ip_address',     'TEXT'),
        ('switch_name',    'TEXT'),
        ('switch_port',    'TEXT'),
        ('netbox_iface_id','INTEGER'),
    ]:
        if col not in existing:
            cur.execute(f'ALTER TABLE customers ADD COLUMN {col} {defn}')
    conn.commit()
    print('Schema ready.')

    # ── 1. Fetch all Splynx online sessions ──────────────────────────────────
    print('Fetching Splynx online sessions...')
    sessions = _sp_get('admin/customers/customers-online', {'per_page': 10000, 'page': 0})
    print(f'  {len(sessions)} active sessions found')

    # Build: splynx_customer_id → {mac, ipv4}
    # Sessions for the same customer_id shouldn't occur but handle gracefully
    cx_session: dict[int, dict] = {}
    for s in sessions:
        cx_id_sp = s.get('customer_id')
        mac_raw   = (s.get('mac') or '').strip()
        ipv4      = (s.get('ipv4') or '').strip()
        if not cx_id_sp or not mac_raw:
            continue
        mac = normalize_mac(mac_raw)
        cx_session[int(cx_id_sp)] = {'mac': mac, 'ip': ipv4 or None}

    print(f'  {len(cx_session)} unique customers with active sessions')

    # ── 2. Fetch rosctl device list ───────────────────────────────────────────
    print('Fetching rosctl device list...')
    devices_data = _ros_get('devices', {'limit': 500})
    all_devices = devices_data.get('devices', [])
    switches = [d for d in all_devices if d.get('device_role') == 'Switch' or d.get('role') == 'Switch']
    print(f'  {len(switches)} switches')

    # ── 3. Build MAC → switch port from bridge-host tables ───────────────────
    print('Fetching bridge-host tables from all switches...')
    mac_to_port: dict[str, dict] = {}
    switch_errors = 0

    def fetch_bridge_hosts(sw):
        try:
            result = _ros_command(sw['id'], '/interface/bridge/host/print detail')
            hosts = result.get('data', [])
            local_map = {}
            for h in hosts:
                mac_raw = (h.get('mac_address') or '').strip()
                if not mac_raw:
                    continue
                mac = normalize_mac(mac_raw)
                ros_port = h.get('on_interface') or h.get('interface') or ''
                if not mac or not ros_port:
                    continue
                eth_port = ros_port_to_eth(ros_port)
                if not eth_port:
                    continue
                local_map[mac] = {
                    'switch_name': sw['name'],
                    'ros_port':    ros_port,
                    'eth_port':    eth_port,
                }
            return sw['name'], local_map, None
        except Exception as e:
            return sw['name'], {}, str(e)

    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(fetch_bridge_hosts, s): s for s in switches}
        done = 0
        for fut in as_completed(futs):
            sname, local_map, err = fut.result()
            done += 1
            if err:
                switch_errors += 1
                print(f'  WARNING: {sname}: {err}')
            else:
                for mac, info in local_map.items():
                    if mac not in mac_to_port:
                        mac_to_port[mac] = info
            if done % 20 == 0:
                print(f'  {done}/{len(switches)} switches done...')

    print(f'  {len(mac_to_port)} unique subscriber MACs in bridge tables ({switch_errors} switch errors)')

    # ── 4. Build NetBox interface lookup ──────────────────────────────────────
    print('Building NetBox interface lookup...')
    nb_iface_map: dict[tuple, int] = {}
    nb_devices = _nb_get('dcim/devices/', {'limit': 500, 'role': 'switch'})
    for dev in nb_devices.get('results', []):
        dev_name = dev['name']
        try:
            ifaces = _nb_get('dcim/interfaces/', {'device': dev_name, 'limit': 200})
            for iface in ifaces.get('results', []):
                nb_iface_map[(dev_name, iface['name'])] = iface['id']
        except Exception:
            pass
    print(f'  {len(nb_iface_map)} NetBox interfaces indexed')

    # ── 5. Load customers from DB — focus on those without PPP linkage ────────
    customers = cur.execute('''
        SELECT id, splynx_id FROM customers
        WHERE splynx_id IS NOT NULL AND status = 'active' AND router_name IS NULL
    ''').fetchall()
    print(f'\nLinking {len(customers)} non-PPP active customers...')

    updated = 0
    session_matched = 0
    port_matched = 0
    nb_matched = 0
    no_session = 0
    no_port = 0

    for cx in customers:
        cx_id     = cx['id']
        sp_id     = cx['splynx_id']

        session = cx_session.get(sp_id)
        if not session:
            no_session += 1
            continue
        session_matched += 1

        mac = session['mac']
        ip  = session['ip']

        port_info = mac_to_port.get(mac)
        if not port_info:
            no_port += 1
            # Still save the IP even without a port match
            if ip:
                cur.execute('UPDATE customers SET ip_address=? WHERE id=?', (ip, cx_id))
                updated += 1
            continue
        port_matched += 1

        switch_name = port_info['switch_name']
        switch_port = port_info['eth_port']
        nb_iface_id = nb_iface_map.get((switch_name, switch_port))
        if nb_iface_id:
            nb_matched += 1

        cur.execute('''
            UPDATE customers
            SET ip_address=?, switch_name=?, switch_port=?, netbox_iface_id=?
            WHERE id=?
        ''', (ip, switch_name, switch_port, nb_iface_id, cx_id))
        updated += 1

        if updated % 500 == 0:
            conn.commit()
            print(f'  {updated} updated...')

    conn.commit()

    print(f'\n── DHCP Linkage Results ─────────────────────────────────────────')
    print(f'  Non-PPP active customers:    {len(customers)}')
    print(f'  Active Splynx session found: {session_matched} ({100*session_matched//max(len(customers),1)}%)')
    print(f'  Switch port matched:         {port_matched} ({100*port_matched//max(session_matched,1)}% of sessioned)')
    print(f'  NetBox interface matched:    {nb_matched}')
    print(f'  No session (offline):        {no_session}')
    print(f'  Session found, no bridge-host: {no_port}')
    print(f'  DB rows updated:             {updated}')

    # Sample output
    print('\nSample DHCP-linked customers:')
    rows = cur.execute('''
        SELECT name, ip_address, switch_name, switch_port, netbox_iface_id
        FROM customers
        WHERE switch_name IS NOT NULL AND router_name IS NULL AND ip_address IS NOT NULL
        LIMIT 10
    ''').fetchall()
    for r in rows:
        print(f'  {r[0]} | {r[1]} | {r[2]}:{r[3]} | nb_iface={r[4]}')

    # Overall summary
    totals = cur.execute('''
        SELECT
          COUNT(*) as total,
          SUM(CASE WHEN router_name IS NOT NULL THEN 1 ELSE 0 END) as ppp_linked,
          SUM(CASE WHEN switch_name IS NOT NULL THEN 1 ELSE 0 END) as switch_linked,
          SUM(CASE WHEN ip_address IS NOT NULL THEN 1 ELSE 0 END) as has_ip,
          SUM(CASE WHEN router_name IS NULL AND switch_name IS NULL THEN 1 ELSE 0 END) as unlinked
        FROM customers WHERE status="active"
    ''').fetchone()
    print(f'\n── Overall Active Customer Linkage ─────────────────────────────')
    print(f'  Total active:    {totals[0]}')
    print(f'  PPP-linked:      {totals[1]} ({100*totals[1]//max(totals[0],1)}%)')
    print(f'  Switch-linked:   {totals[2]} ({100*totals[2]//max(totals[0],1)}%)')
    print(f'  Has IP:          {totals[3]} ({100*totals[3]//max(totals[0],1)}%)')
    print(f'  Fully unlinked:  {totals[4]} ({100*totals[4]//max(totals[0],1)}%)')

    conn.close()


if __name__ == '__main__':
    main()
