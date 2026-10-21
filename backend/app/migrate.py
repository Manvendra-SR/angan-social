"""Bring an existing database up to date with the models.

    python -m app.migrate

create_all() only creates *missing tables*; it never adds columns or indexes to
tables that already exist. This script applies those additions explicitly. It
is idempotent (safe to run any number of times) and purely additive: it never
drops tables, columns or data.

Steps:
  1. stop if existing users would collide once usernames/emails are compared
     ignoring case (a person must rename one account first)
  2. case-insensitive unique indexes on users.username / users.email
  3. messages.idempotency_key column + its unique index
  4. create any new tables (notifications, conversation_reads)
"""
import sys
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.models import Base
from app.models.message import Message
from app.models.user import EMAIL_LOWER_INDEX, USERNAME_LOWER_INDEX

COLLISION_QUERIES = {
    "username": "SELECT lower(username), count(*) FROM users GROUP BY 1 HAVING count(*) > 1",
    "email": "SELECT lower(email), count(*) FROM users GROUP BY 1 HAVING count(*) > 1",
}


def find_collisions(conn) -> dict[str, list]:
    if not conn.execute(text("SELECT to_regclass('users')")).scalar():
        return {}  # fresh database: nothing to check
    return {
        field: rows
        for field, query in COLLISION_QUERIES.items()
        if (rows := conn.execute(text(query)).all())
    }


def migrate(engine) -> None:
    with engine.begin() as conn:
        collisions = find_collisions(conn)
        if collisions:
            for field, rows in collisions.items():
                for value, count in rows:
                    print(f"  {count} accounts share the {field} '{value}' (ignoring case)")
            sys.exit("Rename the duplicate accounts, then run this again. Nothing was changed.")

        # new tables first, so a fresh database gets everything from the models
        Base.metadata.create_all(conn)
        print("tables: ok")

        for index in (USERNAME_LOWER_INDEX, EMAIL_LOWER_INDEX):
            index.create(conn, checkfirst=True)
            print(f"index {index.name}: ok")

        # additive column on an existing table; NULL for all old messages
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64)"))
        print("column messages.idempotency_key: ok")
        for index in Message.__table__.indexes:
            index.create(conn, checkfirst=True)
            print(f"index {index.name}: ok")


def main():
    # DDL goes over the direct (non-pooled) connection
    engine = create_engine(settings.DATABASE_URL)
    print(f"Database host: {engine.url.host}")
    migrate(engine)
    print("Migration complete.")


if __name__ == "__main__":
    main()
