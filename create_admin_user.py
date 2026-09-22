# create_admin_user.py
# ─────────────────────────────────────────────────────────────
# Creates a new admin user, or resets an existing one's password if the
# username already exists - useful for account recovery when locked out.
#
# Usage (prompts for anything not passed):
#   python create_admin_user.py
#   python create_admin_user.py --username admin --email admin@example.com
# ─────────────────────────────────────────────────────────────

import argparse
import getpass

from werkzeug.security import generate_password_hash

import database as db


def upsert_admin(username, email, password, role="admin", force_password_change=False):
    password_hash = generate_password_hash(password)
    conn = db.get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (username, email, password_hash, role, is_temporary_password)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET
                email = EXCLUDED.email,
                password_hash = EXCLUDED.password_hash,
                role = EXCLUDED.role,
                is_temporary_password = EXCLUDED.is_temporary_password
            RETURNING id, (xmax = 0) AS inserted;
        """, (username, email, password_hash, role, force_password_change))
        user_id, was_inserted = cur.fetchone()
        conn.commit()
        return user_id, was_inserted
    finally:
        cur.close()
        conn.close()


def main():
    p = argparse.ArgumentParser(description="Create or reset an admin user.")
    p.add_argument("--username", help="Login username")
    p.add_argument("--email", help="Email address")
    p.add_argument("--password", help="New password (omit to be prompted securely)")
    p.add_argument("--role", default="admin", choices=["admin", "manager"],
                   help="Role to grant (default: admin)")
    p.add_argument("--force_password_change", action="store_true",
                   help="Mark the password as temporary, forcing a change on next login")
    args = p.parse_args()

    username = args.username or input("Username: ").strip()
    email = args.email or input("Email: ").strip()
    password = args.password or getpass.getpass("New password: ")
    confirm = args.password or getpass.getpass("Confirm password: ")

    if not args.password and password != confirm:
        print("Passwords don't match - aborting.")
        return

    if not username or not email or not password:
        print("Username, email, and password are all required - aborting.")
        return

    user_id, was_inserted = upsert_admin(
        username, email, password, role=args.role,
        force_password_change=args.force_password_change,
    )

    action = "Created" if was_inserted else "Reset password for"
    print(f"{action} user '{username}' (id={user_id}), role='{args.role}'.")


if __name__ == "__main__":
    main()
