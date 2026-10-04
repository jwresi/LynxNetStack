#!/usr/bin/env python3
"""
Import customers and service plans from Splynx into LynxMSP SQLite DB.
Run inside the backend container:
  docker exec lynxmsp-backend python3 /app/scripts/import_splynx.py
"""
import sys, os, time, hmac, hashlib, sqlite3, re
import urllib.request, urllib.parse, json

sys.path.insert(0, '/app')

BASE    = 'https://crm.resibridge.com'
KEY     = 'bd793c726617bee375996ccbb1c8d092'
SECRET  = '9d4124dedfd3cb7ce75aecc70f432d7e'
DB_PATH = '/app/data/lynxcrm.db'

# ── Splynx helpers ──────────────────────────────────────────────────────────

def _get_token():
    nonce = int(time.time())
    msg   = f'{nonce}{KEY}'
    sig   = hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest().upper()
    body  = json.dumps({'auth_type': 'api_key', 'key': KEY, 'signature': sig, 'nonce': nonce}).encode()
    req   = urllib.request.Request(f'{BASE}/api/2.0/admin/auth/tokens', data=body,
                headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())['access_token']

_TOKEN_CACHE = [None, 0]

def _token():
    now = time.time()
    if _TOKEN_CACHE[0] is None or now - _TOKEN_CACHE[1] > 240:
        _TOKEN_CACHE[0] = _get_token()
        _TOKEN_CACHE[1] = now
    return _TOKEN_CACHE[0]

def splynx(path, params=None):
    url = f'{BASE}/api/2.0/{path.lstrip("/")}'
    if params:
        url += '?' + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={'Authorization': f'Splynx-EA (access_token={_token()})'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

# ── Sanitization helpers ────────────────────────────────────────────────────

def clean_phone(raw):
    if not raw:
        return None
    digits = re.sub(r'\D', '', str(raw))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) == 10:
        return f'({digits[:3]}) {digits[3:6]}-{digits[6:]}'
    return str(raw).strip() or None

def clean_email(raw):
    if not raw:
        return None
    e = str(raw).strip().lower()
    if '@' not in e or '.' not in e.split('@')[-1]:
        return None
    return e

def clean_name(raw):
    if not raw:
        return None
    n = str(raw).strip()
    # Remove obvious placeholder / test names
    if re.match(r'^(test|demo|sample|unknown|n/?a)$', n, re.I):
        return None
    return n

def clean_address(street, city, zip_code):
    parts = [p.strip() for p in [street, city, zip_code] if p and str(p).strip()]
    return ', '.join(parts) or None

def map_status(splynx_status):
    return {
        'active':   'active',
        'new':      'pending',
        'blocked':  'suspended',
        'disabled': 'inactive',
    }.get(str(splynx_status).lower(), 'inactive')

# ── Main import ─────────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── 1. Clear test data (only @example.com placeholder addresses) ────────
    test_cids = [row[0] for row in cur.execute(
        "SELECT id FROM customers WHERE email LIKE '%@example.com'"
    ).fetchall()]
    if test_cids:
        placeholders = ','.join('?' * len(test_cids))
        cur.execute(f'DELETE FROM invoices   WHERE customer_id IN ({placeholders})', test_cids)
        cur.execute(f'DELETE FROM tickets    WHERE customer_id IN ({placeholders})', test_cids)
        cur.execute(f'DELETE FROM customers  WHERE id IN ({placeholders})', test_cids)
        conn.commit()
        print(f'Removed {len(test_cids)} test customer(s).')

    # ── 2. Import service plans ─────────────────────────────────────────────
    print('Fetching Splynx tariff plans...')
    plans = splynx('admin/tariffs/internet')
    plan_id_map = {}  # splynx tariff_id -> lynxmsp service_plan id

    for p in plans:
        title = str(p.get('title') or p.get('service_name') or '').strip()
        if not title:
            continue
        price = float(p.get('price') or 0)
        dl    = int(p.get('speed_download') or 0)  # kbps
        ul    = int(p.get('speed_upload')   or 0)
        splynx_id = int(p['id'])

        row = cur.execute('SELECT id FROM service_plans WHERE name = ?', (title,)).fetchone()
        if row:
            cur.execute(
                'UPDATE service_plans SET monthly_price=?, download_speed=?, upload_speed=? WHERE id=?',
                (price, dl // 1000, ul // 1000, row['id'])
            )
            plan_id_map[splynx_id] = row['id']
        else:
            cur.execute(
                '''INSERT INTO service_plans (name, monthly_price, download_speed, upload_speed,
                   service_type, status, created_at)
                   VALUES (?,?,?,?,'fiber','active',datetime('now'))''',
                (title, price, dl // 1000, ul // 1000)
            )
            plan_id_map[splynx_id] = cur.lastrowid

    conn.commit()
    print(f'  Upserted {len(plan_id_map)} service plans.')

    # ── 3. Build plan map: match customers to plans by MRR price ───────────
    # Splynx doesn't have a bulk services list endpoint; instead we use the
    # customer's mrr_total to find the closest-price plan for each customer.
    # Build a price -> plan_id lookup (prefer exact match).
    price_to_plan = {}
    for splynx_tid, lynx_pid in plan_id_map.items():
        row = cur.execute('SELECT monthly_price FROM service_plans WHERE id=?', (lynx_pid,)).fetchone()
        if row:
            price_to_plan[round(float(row['monthly_price']), 2)] = lynx_pid

    def find_plan_by_mrr(mrr_str):
        try:
            mrr = round(float(mrr_str or 0), 2)
            if mrr > 0 and mrr in price_to_plan:
                return price_to_plan[mrr]
        except (ValueError, TypeError):
            pass
        return None

    # ── 4. Import customers ─────────────────────────────────────────────────
    print('Fetching Splynx customers...')
    customers = splynx('admin/customers/customer', {'page': 0, 'per_page': 10000})
    print(f'  Got {len(customers)} customers from Splynx.')

    inserted = updated = skipped = 0

    for c in customers:
        splynx_id = int(c['id'])
        name = clean_name(c.get('name'))
        if not name:
            skipped += 1
            continue

        email        = clean_email(c.get('email') or c.get('billing_email'))
        phone        = clean_phone(c.get('phone'))
        address      = clean_address(c.get('street_1'), c.get('city'), c.get('zip_code'))
        status       = map_status(c.get('status', 'disabled'))
        plan_id      = find_plan_by_mrr(c.get('mrr_total'))
        splynx_login = str(c.get('login') or '').strip() or None

        # Upsert: match by splynx_id first, then email
        existing = cur.execute('SELECT id FROM customers WHERE splynx_id = ?', (splynx_id,)).fetchone()
        if not existing and email:
            existing = cur.execute('SELECT id FROM customers WHERE email = ?', (email,)).fetchone()

        if existing:
            cur.execute('''UPDATE customers SET name=?, email=?, phone=?, address=?, status=?,
                           service_plan_id=?, splynx_id=?, splynx_login=? WHERE id=?''',
                (name, email, phone, address, status, plan_id, splynx_id, splynx_login, existing['id']))
            updated += 1
        else:
            cur.execute('''INSERT INTO customers
                (name, email, phone, address, status, service_plan_id, splynx_id, splynx_login, created_at)
                VALUES (?,?,?,?,?,?,?,?,datetime('now'))''',
                (name, email, phone, address, status, plan_id, splynx_id, splynx_login))
            inserted += 1

        if (inserted + updated) % 500 == 0:
            conn.commit()
            print(f'  ...{inserted + updated} processed')

    conn.commit()
    print(f'\nDone. Inserted: {inserted}  Updated: {updated}  Skipped (no name): {skipped}')
    total = cur.execute('SELECT COUNT(*) FROM customers').fetchone()[0]
    print(f'Total customers in DB: {total}')

    status_dist = cur.execute('SELECT status, COUNT(*) FROM customers GROUP BY status').fetchall()
    for row in status_dist:
        print(f'  {row[0]}: {row[1]}')

    conn.close()


if __name__ == '__main__':
    main()
