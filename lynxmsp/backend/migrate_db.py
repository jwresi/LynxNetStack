#!/usr/bin/env python3
"""
Database migration script to add multi-tenant support
"""
import os
import sqlite3
from datetime import datetime

def migrate_database():
    db_path = "lynxcrm.db"
    
    if not os.path.exists(db_path):
        print("Database doesn't exist, will be created fresh")
        return
    
    # Backup existing database
    backup_path = f"lynxcrm_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    print(f"Backing up database to {backup_path}")
    
    # Copy database file
    import shutil
    shutil.copy2(db_path, backup_path)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Add companies table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255),
                domain VARCHAR(255) UNIQUE,
                setup_complete BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Check if company_id column exists in users table
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'company_id' not in columns:
            # Add new columns to users table
            cursor.execute("ALTER TABLE users ADD COLUMN company_id INTEGER")
            cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE users ADD COLUMN is_company_admin BOOLEAN DEFAULT FALSE")
            
            # Update admin user
            cursor.execute("UPDATE users SET is_admin = TRUE WHERE username = 'admin'")
            
        # Add company_id to other tables if they exist
        tables_to_update = ['customers', 'service_plans', 'tickets', 'sites', 'routers', 'service_orders']
        
        for table in tables_to_update:
            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if cursor.fetchone():
                # Check if company_id column exists
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'company_id' not in columns:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN company_id INTEGER")
        
        conn.commit()
        print("Database migration completed successfully")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()