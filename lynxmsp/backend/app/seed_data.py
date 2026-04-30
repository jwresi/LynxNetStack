"""
Production seed data for LynxMSP
Only creates essential system data - no demo/sample content
"""

from .auth import get_password_hash
from .database import SessionLocal, User


def create_seed_data():
    """
    Create minimal production seed data for LynxMSP.
    Only creates a default admin user if none exists.
    No demo data is created - this is for production use.
    """
    db = SessionLocal()
    
    try:
        # Check if any users exist
        existing_users = db.query(User).count()

        if existing_users == 0:
            # Create default admin user only if no users exist
            admin_user = User(
                username="admin",
                email="admin@example.com",
                password_hash=get_password_hash("admin"),
                is_admin=True,
                company_id=None
            )
            db.add(admin_user)
            db.commit()
            print("Created default admin user (username: admin, password: admin)")
            print("IMPORTANT: Change the default password after first login!")
        else:
            print("Users already exist - no seed data created")
        
    except Exception as e:
        print(f"Error creating seed data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_seed_data()