"""Create all tables and seed the first administrator account.

Usage:
    python scripts/init_db.py
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.security import hash_password  # noqa: E402


def main() -> int:
    print("Creating database schema...")
    Base.metadata.create_all(bind=engine)
    print("Schema ready.\n")

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.role == Role.ADMIN))
        if existing is not None:
            print(f"An administrator already exists: {existing.username}")
            return 0

        username = input("Admin username: ").strip()
        email = input("Admin email: ").strip()
        full_name = input("Admin full name: ").strip()

        while True:
            password = getpass.getpass("Admin password (min 10 chars, letters + digits): ")
            if len(password) < 10 or not any(c.isalpha() for c in password) \
                    or not any(c.isdigit() for c in password):
                print("Password does not meet the policy. Try again.")
                continue
            if password != getpass.getpass("Confirm password: "):
                print("Passwords do not match. Try again.")
                continue
            break

        db.add(
            User(
                username=username,
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                role=Role.ADMIN,
                is_active=True,
            )
        )
        db.commit()

    print("\nAdministrator created. You can now sign in at /api/auth/login")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())