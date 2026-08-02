"""Seed the two demo users used to demonstrate role-based access control.

viewer  -- roles [] (public content only)
officer -- roles ["safety_officer"] (can also see gated 1910.147 content)

The safety_officer gate is synthetic -- see db/002_access_control.sql and the
README. Usage: python -m api.seed_users
"""

import os

import psycopg

from api.auth import hash_password

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://rag:ragdev@localhost:5433/rag")

DEMO_USERS = [
    ("viewer", "viewer-pass", []),
    ("officer", "officer-pass", ["safety_officer"]),
]

UPSERT_SQL = """
INSERT INTO users (username, password_hash, roles)
VALUES (%s, %s, %s)
ON CONFLICT (username) DO UPDATE
SET password_hash = EXCLUDED.password_hash, roles = EXCLUDED.roles
"""


def seed(conn):
    with conn.cursor() as cur:
        for username, password, roles in DEMO_USERS:
            cur.execute(UPSERT_SQL, (username, hash_password(password), roles))
    conn.commit()


if __name__ == "__main__":
    with psycopg.connect(DATABASE_URL) as conn:
        seed(conn)
    print(f"seeded {len(DEMO_USERS)} users: {', '.join(u for u, _, _ in DEMO_USERS)}")
