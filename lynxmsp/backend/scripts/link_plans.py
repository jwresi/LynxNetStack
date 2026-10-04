#!/usr/bin/env python3
"""
Second-pass script: fetch internet services per customer from Splynx
and update service_plan_id in the LynxMSP DB using 20 parallel threads.
Run after import_splynx.py:
  docker exec lynxmsp-backend python3 /app/scripts/link_plans.py
"""
import sys, os, time, hmac, hashlib, sqlite3, threading
import urllib.request, json
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE    = 'https://crm.resibridge.com'
KEY     = 'bd793c726617bee375996ccbb1c8d092'
SECRET  = '9d4124dedfd3cb7ce75aecc70f432d7e'
DB_PATH = '/app/data/lynxcrm.db'
WORKERS = 20

_tlock = threading.Lock()
_token_cache = [None, 0]

def _fresh_token():
    nonce = int(time.time())
    msg   = f'{nonce}{KEY}'
    sig   = hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest().upper()
    body  = json.dumps({'auth_type': 'api_key', 'key': KEY, 'signature': sig, 'nonce': nonce}).encode()
    req   = urllib.request.Request(
        f'{BASE}/api/2.0/admin/auth/tokens', data=body,
        headers={'Content-Type': 'application/json'}, method='POST'
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())['access_token']

def token():
    with _tlock:
        now = time.time()
        if _token_cache[0] is None or now - _token_cache[1] > 200:
            _token_cache[0] = _fresh_token()
            _token_cache[1] = now
        return _token_cache[0]

def fetch_tariff(splynx_cid):
    url = f'{BASE}/api/2.0/admin/customers/customer/{splynx_cid}/internet-services'
    req = urllib.request.Request(url, headers={'Authorization': f'Splynx-EA (access_token={token()})'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
            if isinstance(data, list):
                for svc in data:
                    tid = svc.get('tariff_id')
                    if tid:
                        return splynx_cid, int(tid)
    except Exception:
        pass
    return splynx_cid, None

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Build splynx_id list from embedded tag in customers table.
    # We stored splynx customer id order matches import order, but we
    # need the mapping. Use email as key: re-fetch customers from Splynx
    # and match by email to get lynxmsp_id → splynx_id mapping.
    # Simpler: since we imported them in Splynx ID order with INSERT,
    # and Splynx IDs start at 1, we can use the customers-online approach,
    # OR we just re-fetch the customer list and build the mapping by email.

    print('Building splynx_id → lynxmsp_id map...')
    import urllib.parse
    def splynx_get(path, params=None):
        url = f'{BASE}/api/2.0/{path}'
        if params:
            url += '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={'Authorization': f'Splynx-EA (access_token={token()})'})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    # Use splynx_id column directly — much more reliable than email matching
    lynx_rows = cur.execute(
        "SELECT id, splynx_id FROM customers WHERE splynx_id IS NOT NULL AND status IN ('active','pending')"
    ).fetchall()
    pairs = [(r['id'], r['splynx_id']) for r in lynx_rows]

    print(f'  Matched {len(pairs)} active/pending customers for plan linking')

    # Build tariff_id -> lynxmsp plan_id map
    plan_rows = cur.execute(
        "SELECT sp.id, sp.monthly_price FROM service_plans sp WHERE sp.status = 'active'"
    ).fetchall()
    # Also need splynx tariff id -> lynxmsp plan id
    # Since plans were imported in order, re-fetch tariffs from Splynx to get id mapping
    tariffs = splynx_get('admin/tariffs/internet')
    splynx_tariff_title = {int(t['id']): str(t.get('title') or t.get('service_name') or '') for t in tariffs}

    title_to_lynx_plan = {}
    lynx_plans = cur.execute("SELECT id, name FROM service_plans").fetchall()
    for p in lynx_plans:
        title_to_lynx_plan[p['name'].strip()] = p['id']

    tariff_to_plan = {}
    for tid, title in splynx_tariff_title.items():
        if title in title_to_lynx_plan:
            tariff_to_plan[tid] = title_to_lynx_plan[title]

    print(f'  Tariff→plan map: {len(tariff_to_plan)} entries')

    # Threaded fetch of per-customer services
    print(f'Fetching services for {len(pairs)} customers with {WORKERS} workers...')
    start = time.time()
    done = [0]
    lock = threading.Lock()
    updates = []  # (lynxmsp_id, plan_id)

    def worker(pair):
        lynxmsp_id, splynx_id = pair
        _, tariff_id = fetch_tariff(splynx_id)
        plan_id = tariff_to_plan.get(tariff_id) if tariff_id else None
        with lock:
            done[0] += 1
            if done[0] % 500 == 0:
                elapsed = time.time() - start
                rate = done[0] / elapsed
                remaining = (len(pairs) - done[0]) / rate
                print(f'  {done[0]}/{len(pairs)} ({remaining:.0f}s remaining)')
        return lynxmsp_id, plan_id

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(worker, p) for p in pairs]
        for fut in as_completed(futures):
            lynxmsp_id, plan_id = fut.result()
            if plan_id:
                updates.append((plan_id, lynxmsp_id))

    print(f'  Done in {time.time()-start:.0f}s. Updating {len(updates)} plan assignments...')
    for plan_id, lynxmsp_id in updates:
        cur.execute('UPDATE customers SET service_plan_id=? WHERE id=?', (plan_id, lynxmsp_id))
    conn.commit()

    total = cur.execute('SELECT COUNT(*) FROM customers').fetchone()[0]
    with_plan = cur.execute('SELECT COUNT(*) FROM customers WHERE service_plan_id IS NOT NULL').fetchone()[0]
    print(f'\nPlan assignment: {with_plan}/{total} ({with_plan*100//total}%)')

    print('\nTop plans by subscriber count:')
    rows = cur.execute('''SELECT sp.name, COUNT(*) as cnt FROM customers c
        JOIN service_plans sp ON c.service_plan_id = sp.id
        GROUP BY sp.id ORDER BY cnt DESC LIMIT 10''').fetchall()
    for r in rows:
        print(f'  {r[1]:5d} x {r[0]}')

    conn.close()


if __name__ == '__main__':
    main()
