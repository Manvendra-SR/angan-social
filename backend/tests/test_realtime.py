"""WebSocket authentication, routing and event delivery."""
from datetime import timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.realtime import manager
from app.core.security import create_access_token
from app.routers import ws as ws_module

ORIGIN = {"origin": "http://localhost:5173"}


def token_of(headers):
    return headers["Authorization"].split()[1]


def connect(client, token, headers=ORIGIN):
    ws = client.websocket_connect("/ws", headers=headers)
    session = ws.__enter__()
    session.send_json({"type": "auth", "token": token})
    assert session.receive_json() == {"type": "ready"}
    return ws, session


def close_code(session):
    with pytest.raises(WebSocketDisconnect) as exc:
        session.receive_json()
    return exc.value.code


def test_rejects_foreign_origin(client, make_user):
    _, h = make_user("alice")
    with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}) as session:
        assert close_code(session) == 4403


def test_rejects_bad_token_and_wrong_first_message(client):
    with client.websocket_connect("/ws", headers=ORIGIN) as session:
        session.send_json({"type": "auth", "token": "not-a-jwt"})
        assert close_code(session) == 4401
    with client.websocket_connect("/ws", headers=ORIGIN) as session:
        session.send_text("hello")
        assert close_code(session) == 4401


def test_token_for_deleted_or_unknown_user_rejected(client):
    token = create_access_token({"sub": "999999"})
    with client.websocket_connect("/ws", headers=ORIGIN) as session:
        session.send_json({"type": "auth", "token": token})
        assert close_code(session) == 4401


def test_auth_timeout(client, monkeypatch):
    monkeypatch.setattr(ws_module, "AUTH_TIMEOUT_SECONDS", 0.2)
    with client.websocket_connect("/ws", headers=ORIGIN) as session:
        assert close_code(session) == 4408


def test_socket_closed_when_token_expires(client, make_user):
    alice, _ = make_user("alice")
    token = create_access_token({"sub": str(alice["id"])}, expires_delta=timedelta(seconds=2))
    ws, session = connect(client, token)
    assert close_code(session) == 4401
    ws.__exit__(None, None, None)


def test_message_reaches_participants_only(client, make_user):
    alice, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    carol, carol_h = make_user("carol")
    cid = client.post("/conversations", json={"user_id": bob["id"]}, headers=alice_h).json()["id"]

    sockets = {name: connect(client, token_of(h)) for name, h in
               [("alice", alice_h), ("bob", bob_h), ("carol", carol_h)]}
    try:
        msg = client.post(f"/conversations/{cid}/messages", json={"body": "hi bob"}, headers=alice_h).json()

        bob_event = sockets["bob"][1].receive_json()
        assert bob_event == {"type": "message.created", "conversation_id": cid, "message": msg}
        assert sockets["bob"][1].receive_json() == {
            "type": "counts.updated", "unread_messages": 1, "unread_notifications": 0,
        }
        # the sender's own tabs get the message too
        assert sockets["alice"][1].receive_json()["message"]["id"] == msg["id"]

        # carol got nothing: the first event she sees is the one we trigger now
        client.post("/notifications/read-all", headers=carol_h)
        assert sockets["carol"][1].receive_json()["type"] == "counts.updated"
    finally:
        for ws, _ in sockets.values():
            ws.__exit__(None, None, None)


def test_like_pushes_notification_and_counts(client, make_user):
    _, alice_h = make_user("alice")
    _, bob_h = make_user("bob")
    post = client.post("/posts", data={"content": "p"}, headers=alice_h).json()

    ws, session = connect(client, token_of(alice_h))
    try:
        client.post(f"/likes/{post['id']}", headers=bob_h)
        created = session.receive_json()
        assert created["type"] == "notification.created"
        assert created["notification"]["type"] == "like"
        assert created["notification"]["post_id"] == post["id"]
        assert session.receive_json() == {
            "type": "counts.updated", "unread_notifications": 1, "unread_messages": 0,
        }
        # a failed duplicate like pushes nothing; marking read pushes fresh counts
        assert client.post(f"/likes/{post['id']}", headers=bob_h).status_code == 409
        client.post(f"/notifications/{created['notification']['id']}/read", headers=alice_h)
        assert session.receive_json()["unread_notifications"] == 0
    finally:
        ws.__exit__(None, None, None)


def test_every_tab_receives_events_and_disconnect_cleans_up(client, make_user):
    alice, alice_h = make_user("alice")
    tab1, s1 = connect(client, token_of(alice_h))
    tab2, s2 = connect(client, token_of(alice_h))
    assert len(manager.connections[alice["id"]]) == 2

    client.post("/notifications/read-all", headers=alice_h)
    assert s1.receive_json()["type"] == "counts.updated"
    assert s2.receive_json()["type"] == "counts.updated"

    tab1.__exit__(None, None, None)
    assert len(manager.connections[alice["id"]]) == 1
    tab2.__exit__(None, None, None)
    assert not manager.is_connected(alice["id"])


def test_offline_user_recovers_over_rest(client, make_user):
    """No socket open: nothing is pushed, but the data is all there afterwards."""
    _, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    cid = client.post("/conversations", json={"user_id": bob["id"]}, headers=alice_h).json()["id"]
    first = client.post(f"/conversations/{cid}/messages", json={"body": "while offline"}, headers=alice_h).json()

    # bob reconnects later: counts + missed messages come from REST
    ws, session = connect(client, token_of(bob_h))
    try:
        assert client.get("/users/me/counts", headers=bob_h).json()["unread_messages"] == 1
        missed = client.get(f"/conversations/{cid}/messages?after_id=0", headers=bob_h).json()
        assert [m["id"] for m in missed] == [first["id"]]
    finally:
        ws.__exit__(None, None, None)
