# ============================================================================
# One-time script: make an account an organizer (admin)
# Run from the backend folder: python make_admin.py your@email.com
# ============================================================================

import sys

from app.database import SessionLocal
from app.models import User


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python make_admin.py your@email.com")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            print(f"No account found for {email}")
            sys.exit(1)
        user.is_admin = True
        db.commit()
        print(f"{email} is now an organizer (admin).")
    finally:
        db.close()


if __name__ == "__main__":
    main()