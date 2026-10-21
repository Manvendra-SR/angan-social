"""Secret validation and case-insensitive identity rules."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import PLACEHOLDER_SECRET_KEY, Settings
from app.core.database import engine
from app.core.db_errors import constraint_name, user_conflict

BASE_SETTINGS = dict(
    _env_file=None,
    DATABASE_URL="postgresql://u:p@localhost/db",
    CLOUDINARY_CLOUD_NAME="c", CLOUDINARY_API_KEY="k", CLOUDINARY_API_SECRET="s",
)


@pytest.mark.parametrize("bad_key", ["too-short", PLACEHOLDER_SECRET_KEY])
def test_weak_secret_key_rejected_without_echoing_it(bad_key):
    with pytest.raises(ValidationError) as exc:
        Settings(SECRET_KEY=bad_key, **BASE_SETTINGS)
    assert "SECRET_KEY must be at least" in str(exc.value)
    assert bad_key not in str(exc.value)


def test_missing_secret_key_rejected(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(**BASE_SETTINGS)


def test_strong_secret_key_is_masked():
    settings = Settings(SECRET_KEY="x" * 40, **BASE_SETTINGS)
    assert settings.SECRET_KEY.get_secret_value() == "x" * 40
    assert "x" * 40 not in repr(settings)


def register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def test_username_unique_ignoring_case_but_keeps_display_casing(client):
    r = register(client, "Manav", "manav@example.com")
    assert r.status_code == 201 and r.json()["username"] == "Manav"
    r = register(client, "manav", "other@example.com")
    assert r.status_code == 409 and r.json()["detail"] == "Username already taken"


def test_email_stored_lowercase_and_unique_ignoring_case(client):
    r = register(client, "alice", "Alice@Example.COM")
    assert r.status_code == 201 and r.json()["email"] == "alice@example.com"
    r = register(client, "alice2", "ALICE@example.com")
    assert r.status_code == 409 and r.json()["detail"] == "Email already registered"
    # login is case-insensitive for the email too
    login = client.post("/auth/login", data={"username": "ALICE@EXAMPLE.com", "password": "password123"})
    assert login.status_code == 200


def test_rename_to_case_variant_of_another_user(client, make_user):
    make_user("bob")
    _, alice_h = make_user("alice")
    r = client.patch("/users/me", json={"username": "BOB"}, headers=alice_h)
    assert r.status_code == 409 and r.json()["detail"] == "Username already taken"
    # changing only your own casing is fine
    r = client.patch("/users/me", json={"username": "Alice"}, headers=alice_h)
    assert r.status_code == 200 and r.json()["username"] == "Alice"


def test_database_rejects_case_variants_directly():
    """The invariant holds even if the Python pre-check is bypassed."""
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO users (username, email, password_hash, is_private) VALUES ('Race', 'race@x.com', 'x', false)"
        ))
        with pytest.raises(IntegrityError) as exc:
            conn.execute(text(
                "INSERT INTO users (username, email, password_hash, is_private) VALUES ('race', 'race2@x.com', 'x', false)"
            ))
        conn.rollback()
    assert constraint_name(exc.value) == "uq_users_username_lower"
    assert user_conflict(exc.value).status_code == 409


def test_concurrent_case_variant_registrations(client):
    """Two simultaneous sign-ups for Race/race: exactly one wins, the other gets 409 (never 500)."""
    for round_ in range(3):
        names = [f"Racer{round_}", f"racer{round_}"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda n: register(client, n, f"{n.lower()}{names.index(n)}@example.com").status_code, names
            ))
        assert sorted(results) == [201, 409], results
