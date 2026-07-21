#!/usr/bin/env python3
"""
AD Report Hub — Create Admin User
=================================
Usage:
    python create_admin.py
"""

import sys
import os
import getpass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, User


def main():
    app = create_app()
    with app.app_context():
        print("\n── AD Report Hub Admin Creation ──────────────────────")

        username = input("  Username : ").strip()
        email    = input("  E-mail   : ").strip()
        password = getpass.getpass("  Password : ")
        confirm  = getpass.getpass("  Confirm  : ")

        if password != confirm:
            print("  ✘  As senhas não coincidem.")
            sys.exit(1)

        if not username or not email or not password:
            print("  ✖  All fields are required.")
            sys.exit(1)

        if User.query.filter_by(username=username).first():
            print(f"  ✖  Username '{username}' already exists.")
            sys.exit(1)

        user = User(username=username, email=email, is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        print(f"\n  ✔  Admin user '{username}' created successfully.")
        print("─────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
