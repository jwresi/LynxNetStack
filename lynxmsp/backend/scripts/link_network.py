#!/usr/bin/env python3
"""
Link customers to their switch port and router via PPP sessions and bridge-host tables.

Chain: splynx_login == PPP session name → caller_id (MAC) → bridge-host → switch:port → NetBox interface

Run inside the backend container:
  docker exec lynxmsp-backend python3 /app/scripts/link_network.py
"""
import sys, os, time, sqlite3, json, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_PATH   = '/app/data/lynxcrm.db'
ROSCTL    = 'http://172.27.226.246:3200'
NETBOX    = 'http://172.27.48.233:8001'
NB_TOKEN  = '8fd77834b1412f49a09e768be1b379f5416f33c3'
ROS_USER  = 'jonathan'
ROS_PASS  = 'F7pdn*AQ0Uu4S#t'

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

# ── Helpers ───────────────────────────────────────────────────────────────────

def ros_port_to_eth(port_name):
    """Map RouterOS interface name to NetBox ETH{N} convention."""
    import re
    # ether17 → ETH17,  sfp-sfpplus1 → SFP+1,  bridge → skip
    m = re.match(r'ether(\d+)$', port_name, re.I)
    if m:
        return f'ETH{m.group(1)}'
    m = re.match(r'sfp-sfpplus(\d+)$', port_name, re.I)
    if m:
        return f'SFP+{m.group(1)}'
    return None  # uplink/bridge/management ports — not a subscriber port


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Migrate: add columns if missing ──────────────────────────────────────
    existing = {r[1] for r in cur.execute('PRAGMA table_info(customers)').fetchall()}
    for col, defn in [
        ('router_name',    'TEXT'),
        ('ppp_ip',         'TEXT'),
        ('switch_name',    'TEXT'),
        ('switch_port',    'TEXT'),
        ('netbox_iface_id','INTEGER'),
    ]:
        if col not in existing:
            cur.execute(f'ALTER TABLE customers ADD COLUMN {col} {defn}')
    conn.commit()
    print('Schema ready.')

    # ── 1. Fetch all rosctl devices ───────────────────────────────────────────
    print('Fetching rosctl device list...')
    devices_data = _ros_get('devices', {'limit': 500})
    all_devices = devices_data.get('devices', [])
    routers = [d for d in all_devices if d.get('device_role') == 'Router' or d.get('role') == 'Router']
    switches = [d for d in all_devices if d.get('device_role') == 'Switch' or d.get('role') == 'Switch']
    print(f'  {len(routers)} routers, {len(switches)} switches')

    # ── 2. Fetch all PPP sessions from all routers ────────────────────────────
    print('Fetching PPP sessions from all routers...')
    # login_name → {router_name, ip, mac}
    ppp_map: dict[str, dict] = {}
    router_errors = 0

    def fetch_ppp(router):
        try:
            result = _ros_command(router['id'], '/ppp/active/print detail')
            sessions = result.get('data', [])
            local_map = {}
            for s in sessions:
                name = s.get('name', '').strip()
                if not name:
                    continue
                local_map[name] = {
                    'router_name': router['name'],
                    'ppp_ip':      s.get('address', '').strip() or None,
                    'mac':         (s.get('caller_id') or '').strip().upper() or None,
                }
            return router['name'], local_map, None
        except Exception as e:
            return router['name'], {}, str(e)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(fetch_ppp, r): r for r in routers}
        for fut in as_completed(futs):
            rname, local_map, err = fut.result()
            if err:
                router_errors += 1
                print(f'  WARNING: {rname}: {err}')
            else:
                ppp_map.update(local_map)

    print(f'  {len(ppp_map)} PPP sessions found ({router_errors} router errors)')

    # ── 3. Build MAC → (switch_name, ether_port) from bridge-host tables ──────
    print('Fetching bridge-host tables from all switches...')
    mac_to_port: dict[str, dict] = {}  # MAC → {switch_name, ros_port, eth_port}
    switch_errors = 0

    def fetch_bridge_hosts(sw):
        try:
            result = _ros_command(sw['id'], '/interface/bridge/host/print detail')
            hosts = result.get('data', [])
            local_map = {}
            for h in hosts:
                mac = (h.get('mac_address') or '').strip().upper()
                ros_port = h.get('on_interface') or h.get('interface') or ''
                if not mac or not ros_port:
                    continue
                # Skip uplink/bridge/management ports
                eth_port = ros_port_to_eth(ros_port)
                if not eth_port:
                    continue
                # Only record subscriber-facing ports (ETH1–ETH48, SFP+1–SFP+4)
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
                # Don't overwrite an existing MAC entry unless we got a more specific port
                for mac, info in local_map.items():
                    if mac not in mac_to_port:
                        mac_to_port[mac] = info
            if done % 20 == 0:
                print(f'  {done}/{len(switches)} switches done...')

    print(f'  {len(mac_to_port)} unique subscriber MACs found ({switch_errors} switch errors)')

    # ── 4. Build NetBox interface lookup: (device_name, eth_port) → iface_id ──
    print('Building NetBox interface lookup...')
    # Fetch all interfaces for switches we care about
    nb_iface_map: dict[tuple, int] = {}  # (device_name, ETH_name) → netbox_id

    # Get all switch device names from NetBox
    nb_devices = _nb_get('dcim/devices/', {'limit': 500, 'role': 'switch'})
    for page in [nb_devices]:
        for dev in page.get('results', []):
            dev_name = dev['name']
            # Fetch interfaces for this device
            try:
                ifaces = _nb_get(f'dcim/interfaces/', {'device': dev_name, 'limit': 200})
                for iface in ifaces.get('results', []):
                    nb_iface_map[(dev_name, iface['name'])] = iface['id']
            except Exception:
                pass

    print(f'  {len(nb_iface_map)} NetBox interfaces indexed')

    # ── 5. Load all customers with splynx_login ───────────────────────────────
    customers = cur.execute(
        'SELECT id, splynx_login FROM customers WHERE splynx_login IS NOT NULL'
    ).fetchall()
    print(f'\nLinking {len(customers)} customers...')

    updated = 0
    ppp_matched = 0
    port_matched = 0
    nb_matched = 0
    no_ppp = 0

    for cx in customers:
        cx_id = cx['id']
        login = cx['splynx_login'].strip()

        # PPP match
        ppp = ppp_map.get(login)
        if not ppp:
            no_ppp += 1
            continue
        ppp_matched += 1

        router_name = ppp['router_name']
        ppp_ip = ppp['ppp_ip']
        mac = ppp['mac']

        # Switch port match via MAC
        port_info = mac_to_port.get(mac) if mac else None
        switch_name = port_info['switch_name'] if port_info else None
        switch_port = port_info['eth_port'] if port_info else None
        if port_info:
            port_matched += 1

        # NetBox interface ID
        nb_iface_id = None
        if switch_name and switch_port:
            nb_iface_id = nb_iface_map.get((switch_name, switch_port))
            if nb_iface_id:
                nb_matched += 1

        cur.execute('''
            UPDATE customers
            SET router_name=?, ppp_ip=?, switch_name=?, switch_port=?, netbox_iface_id=?
            WHERE id=?
        ''', (router_name, ppp_ip, switch_name, switch_port, nb_iface_id, cx_id))
        updated += 1

        if updated % 500 == 0:
            conn.commit()
            print(f'  {updated} updated...')

    conn.commit()

    print(f'\n── Results ─────────────────────────────────────────────')
    print(f'  Customers processed:   {len(customers)}')
    print(f'  PPP session matched:   {ppp_matched} ({100*ppp_matched//len(customers)}%)')
    print(f'  Switch port matched:   {port_matched} ({100*port_matched//max(ppp_matched,1)}% of PPP)')
    print(f'  NetBox iface matched:  {nb_matched}')
    print(f'  No PPP session:        {no_ppp}')

    # Sample output
    print('\nSample linked customers:')
    rows = cur.execute('''
        SELECT name, splynx_login, router_name, ppp_ip, switch_name, switch_port, netbox_iface_id
        FROM customers
        WHERE router_name IS NOT NULL
        LIMIT 8
    ''').fetchall()
    for r in rows:
        print(f'  {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]}:{r[5]} | nb_iface={r[6]}')

    conn.close()


if __name__ == '__main__':
    main()
