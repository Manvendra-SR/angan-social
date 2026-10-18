def register(client, **overrides):
    body = {"username": "alice", "email": "alice@example.com", "password": "password123"}
    body.update(overrides)
    return client.post("/auth/register", json=body)


def test_register_returns_user_without_password(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"
    assert "password" not in body and "password_hash" not in body


def test_register_duplicate_email_and_username(client):
    register(client)
    assert register(client, username="other").status_code == 409
    assert register(client, email="ALICE2@example.com", username="ALICE").status_code == 409


def test_register_validation(client):
    assert register(client, password="short").status_code == 422
    assert register(client, username="no spaces").status_code == 422
    assert register(client, username="ab").status_code == 422
    assert register(client, email="not-an-email").status_code == 422


def test_login_success_and_me(client):
    register(client)
    r = client.post("/auth/login", data={"username": "Alice@Example.com", "password": "password123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_login_invalid_credentials(client):
    register(client)
    wrong_pw = client.post("/auth/login", data={"username": "alice@example.com", "password": "wrongpass1"})
    no_user = client.post("/auth/login", data={"username": "bob@example.com", "password": "password123"})
    assert wrong_pw.status_code == 401
    assert no_user.status_code == 401


def test_protected_endpoint_requires_valid_token(client):
    assert client.get("/users/me").status_code == 401
    bad = client.get("/users/me", headers={"Authorization": "Bearer not.a.token"})
    assert bad.status_code == 401
