"""Add role/full_name/is_active to users and create work_orders table."""
import sqlite3

DB = "data/lynxcrm.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

# ── Users: add missing columns ────────────────────────────────────────────────
existing_cols = {r[1] for r in cur.execute("PRAGMA table_info(users)")}

if "role" not in existing_cols:
    cur.execute("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'cx'")
    print("Added users.role")

if "full_name" not in existing_cols:
    cur.execute("ALTER TABLE users ADD COLUMN full_name VARCHAR")
    print("Added users.full_name")

if "is_active" not in existing_cols:
    cur.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
    print("Added users.is_active")

# Make existing admins role='admin'
cur.execute("UPDATE users SET role='admin' WHERE is_admin=1 OR is_company_admin=1")
print("Updated admin users to role='admin'")

# ── Create work_orders table ──────────────────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR NOT NULL,
    type VARCHAR NOT NULL DEFAULT 'install',
    status VARCHAR NOT NULL DEFAULT 'unscheduled',
    priority VARCHAR NOT NULL DEFAULT 'normal',
    customer_id INTEGER REFERENCES customers(id),
    site_id VARCHAR,
    address TEXT,
    scheduled_start DATETIME,
    scheduled_end DATETIME,
    assigned_to INTEGER REFERENCES users(id),
    ticket_id INTEGER REFERENCES tickets(id),
    notes TEXT,
    checklist JSON DEFAULT '[]',
    photos JSON DEFAULT '[]',
    gps_checkin JSON,
    created_by INTEGER REFERENCES users(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
print("Created work_orders table")

conn.commit()
conn.close()
print("Migration complete.")
