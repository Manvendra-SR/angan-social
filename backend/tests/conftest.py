"""Test setup.

Tests run against TEST_DATABASE_URL (a separate Neon branch). Tables there
are dropped and recreated, so we refuse to run if it isn't set or if it
points at the main database. Cloudinary is replaced with a fake.
"""
import pytest
from sqlalchemy import text, make_url

from app.core.config import settings

if not settings.TEST_DATABASE_URL:
    pytest.exit("TEST_DATABASE_URL is not set; refusing to run tests", returncode=2)
if settings.TEST_DATABASE_URL in (settings.DATABASE_URL, settings.DATABASE_URL_POOLED):
    pytest.exit("TEST_DATABASE_URL must not be the main database", returncode=2)

# Point the app at the test database *before* the engine is created.
settings.DATABASE_URL = settings.TEST_DATABASE_URL
settings.DATABASE_URL_POOLED = None

from app.core.database import engine  # noqa: E402
from app.core import media  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# (no assert: a failing assert would print the URL including the password)
_test_url = make_url(settings.TEST_DATABASE_URL)
if (engine.url.host, engine.url.database, engine.url.username) != (
    _test_url.host, _test_url.database, _test_url.username
):
    pytest.exit("engine is not using TEST_DATABASE_URL; refusing to run", returncode=2)


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


class FakeCloudinary:
    def __init__(self):
        self.uploads = []
        self.deleted = []
        self.fail_with = None

    def upload(self, file, **options):
        if self.fail_with:
            raise self.fail_with
        public_id = f"{options['folder']}/img{len(self.uploads) + 1}"
        self.uploads.append(public_id)
        return {
            "public_id": public_id,
            "secure_url": f"https://res.cloudinary.com/demo/image/upload/{public_id}.jpg",
        }

    def destroy(self, public_id, **options):
        self.deleted.append(public_id)
        return {"result": "ok"}


@pytest.fixture(autouse=True)
def cloudinary_fake(monkeypatch):
    fake = FakeCloudinary()
    monkeypatch.setattr(media.cloudinary.uploader, "upload", fake.upload)
    monkeypatch.setattr(media.cloudinary.uploader, "destroy", fake.destroy)
    return fake


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_user(client):
    """Register + log in a user; returns (user_json, auth_headers)."""
    def _make(username: str, is_private: bool = False, password: str = "password123"):
        r = client.post("/auth/register", json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "is_private": is_private,
        })
        assert r.status_code == 201, r.text
        r2 = client.post("/auth/login", data={
            "username": f"{username}@example.com", "password": password,
        })
        assert r2.status_code == 200, r2.text
        return r.json(), {"Authorization": f"Bearer {r2.json()['access_token']}"}
    return _make


# smallest valid-looking file headers for each format
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 100
