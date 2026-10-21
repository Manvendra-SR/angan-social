"""migrate.py on a database that still has the old schema (test branch only)."""
import pytest
from sqlalchemy import inspect, text

from app.core.database import engine
from app.migrate import migrate


def downgrade_to_old_schema():
    """Recreate the pre-migration state: no new tables, column or indexes."""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS notifications, conversation_reads"))
        conn.execute(text("ALTER TABLE messages DROP COLUMN IF EXISTS idempotency_key"))
        conn.execute(text("DROP INDEX IF EXISTS uq_users_username_lower"))
        conn.execute(text("DROP INDEX IF EXISTS uq_users_email_lower"))


def schema_state():
    insp = inspect(engine)
    return {
        "tables": {"notifications", "conversation_reads"} <= set(insp.get_table_names()),
        "column": "idempotency_key" in {c["name"] for c in insp.get_columns("messages")},
        "user_indexes": {"uq_users_username_lower", "uq_users_email_lower"}
        <= {i["name"] for i in insp.get_indexes("users")},
        "message_index": "uq_messages_sender_idempotency_key" in {i["name"] for i in insp.get_indexes("messages")},
    }


def test_migrate_is_additive_and_idempotent(make_user):
    alice, _ = make_user("alice")
    downgrade_to_old_schema()
    assert not any(schema_state().values())

    migrate(engine)
    assert all(schema_state().values())
    migrate(engine)  # second run is a no-op
    assert all(schema_state().values())

    # existing data survived
    with engine.connect() as conn:
        assert conn.execute(text("SELECT username FROM users WHERE id = :i"), {"i": alice["id"]}).scalar() == "alice"


def test_migrate_stops_on_case_collisions_without_changing_anything():
    downgrade_to_old_schema()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (username, email, password_hash, is_private) VALUES "
            "('Dup', 'dup1@x.com', 'x', false), ('dup', 'dup2@x.com', 'x', false)"
        ))
    with pytest.raises(SystemExit):
        migrate(engine)
    assert not any(schema_state().values())

    # after a person fixes the data, the migration goes through
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET username = 'dup_2' WHERE username = 'dup'"))
    migrate(engine)
    assert all(schema_state().values())
