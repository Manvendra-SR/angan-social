def start(client, headers, user_id):
    return client.post("/conversations", json={"user_id": user_id}, headers=headers)


def send(client, headers, conversation_id, body):
    return client.post(f"/conversations/{conversation_id}/messages", json={"body": body}, headers=headers)


def test_start_conversation_is_idempotent_for_both_users(client, make_user):
    alice, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")

    c1 = start(client, alice_h, bob["id"])
    assert c1.status_code == 200
    assert c1.json()["other_user"]["username"] == "bob"
    c2 = start(client, bob_h, alice["id"])
    assert c2.json()["id"] == c1.json()["id"]
    assert c2.json()["other_user"]["username"] == "alice"


def test_start_conversation_invalid_targets(client, make_user):
    alice, h = make_user("alice")
    assert start(client, h, alice["id"]).status_code == 400
    assert start(client, h, 9999).status_code == 404


def test_send_and_read_messages_in_order(client, make_user):
    _, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    conv = start(client, alice_h, bob["id"]).json()

    for i, h in enumerate([alice_h, bob_h, alice_h]):
        r = send(client, h, conv["id"], f"m{i}")
        assert r.status_code == 201

    msgs = client.get(f"/conversations/{conv['id']}/messages", headers=bob_h).json()
    assert [m["body"] for m in msgs] == ["m0", "m1", "m2"]
    assert msgs[1]["sender_id"] == bob["id"]

    convs = client.get("/conversations", headers=bob_h).json()
    assert len(convs) == 1 and convs[0]["last_message"]["body"] == "m2"


def test_message_pagination_and_polling(client, make_user):
    _, alice_h = make_user("alice")
    bob, _ = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    ids = [send(client, alice_h, cid, f"m{i}").json()["id"] for i in range(5)]

    latest = client.get(f"/conversations/{cid}/messages?limit=2", headers=alice_h).json()
    assert [m["body"] for m in latest] == ["m3", "m4"]
    older = client.get(f"/conversations/{cid}/messages?limit=2&before_id={ids[3]}", headers=alice_h).json()
    assert [m["body"] for m in older] == ["m1", "m2"]
    newer = client.get(f"/conversations/{cid}/messages?after_id={ids[2]}", headers=alice_h).json()
    assert [m["body"] for m in newer] == ["m3", "m4"]
    both = client.get(f"/conversations/{cid}/messages?after_id=1&before_id=3", headers=alice_h)
    assert both.status_code == 400


def test_outsider_cannot_read_or_send(client, make_user):
    _, alice_h = make_user("alice")
    bob, _ = make_user("bob")
    _, eve_h = make_user("eve")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    send(client, alice_h, cid, "private")

    assert client.get(f"/conversations/{cid}/messages", headers=eve_h).status_code == 404
    assert send(client, eve_h, cid, "intrusion").status_code == 404
    assert client.get("/conversations", headers=eve_h).json() == []
    assert client.get("/conversations/9999/messages", headers=alice_h).status_code == 404


def test_sender_cannot_be_spoofed(client, make_user):
    alice, alice_h = make_user("alice")
    bob, _ = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]

    r = client.post(
        f"/conversations/{cid}/messages",
        json={"body": "hi", "sender_id": bob["id"]},
        headers=alice_h,
    )
    assert r.status_code == 201
    assert r.json()["sender_id"] == alice["id"]


def test_message_validation(client, make_user):
    _, alice_h = make_user("alice")
    bob, _ = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    assert send(client, alice_h, cid, "   ").status_code == 422
    assert send(client, alice_h, cid, "x" * 2001).status_code == 422


def test_blocked_users_cannot_message(client, make_user):
    alice, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    client.post(f"/follows/{bob['id']}/block", headers=alice_h)

    assert send(client, bob_h, cid, "hey").status_code == 403
    assert start(client, bob_h, alice["id"]).status_code == 403
    # history is still readable by participants
    assert client.get(f"/conversations/{cid}/messages", headers=bob_h).status_code == 200


# ---------- unread tracking ----------

def counts(client, headers):
    return client.get("/users/me/counts", headers=headers).json()


def test_unread_counts_and_read_marker(client, make_user):
    alice, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    m1 = send(client, alice_h, cid, "one").json()
    m2 = send(client, alice_h, cid, "two").json()

    # only the recipient has unread messages; messages never create notifications
    assert counts(client, bob_h) == {"unread_messages": 2, "unread_notifications": 0}
    assert counts(client, alice_h)["unread_messages"] == 0
    assert client.get("/conversations", headers=bob_h).json()[0]["unread_count"] == 2
    assert client.get(f"/conversations/{cid}", headers=bob_h).json()["unread_count"] == 2

    r = client.post(f"/conversations/{cid}/read", json={"last_read_message_id": m1["id"]}, headers=bob_h)
    assert r.status_code == 200 and r.json()["unread_messages"] == 1
    client.post(f"/conversations/{cid}/read", json={"last_read_message_id": m2["id"]}, headers=bob_h)
    assert counts(client, bob_h)["unread_messages"] == 0

    # a stale tab can't move the marker backwards
    client.post(f"/conversations/{cid}/read", json={"last_read_message_id": m1["id"]}, headers=bob_h)
    assert counts(client, bob_h)["unread_messages"] == 0

    # replying doesn't make my own message unread for me
    send(client, bob_h, cid, "reply")
    assert counts(client, bob_h)["unread_messages"] == 0
    assert counts(client, alice_h)["unread_messages"] == 1


def test_read_marker_validation(client, make_user):
    _, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    carol, carol_h = make_user("carol")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    other_cid = start(client, alice_h, carol["id"]).json()["id"]
    other_msg = send(client, alice_h, other_cid, "for carol").json()
    send(client, alice_h, cid, "for bob")

    # a message from another conversation, a missing id, an outsider
    assert client.post(f"/conversations/{cid}/read", json={"last_read_message_id": other_msg["id"]}, headers=bob_h).status_code == 404
    assert client.post(f"/conversations/{cid}/read", json={"last_read_message_id": 999999}, headers=bob_h).status_code == 404
    assert client.post(f"/conversations/{cid}/read", json={"last_read_message_id": other_msg["id"]}, headers=carol_h).status_code == 404
    assert client.get(f"/conversations/{cid}", headers=carol_h).status_code == 404


def test_get_conversation_shows_other_user(client, make_user):
    _, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    assert client.get(f"/conversations/{cid}", headers=alice_h).json()["other_user"]["username"] == "bob"


# ---------- idempotent sends ----------

def send_with_key(client, headers, cid, body, key):
    return client.post(
        f"/conversations/{cid}/messages", json={"body": body},
        headers={**headers, "Idempotency-Key": key},
    )


def message_count(client, headers, cid):
    return len(client.get(f"/conversations/{cid}/messages?limit=100", headers=headers).json())


def test_retry_with_same_key_returns_existing_message(client, make_user):
    _, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]

    first = send_with_key(client, alice_h, cid, "hello", "key-abc-123")
    retry = send_with_key(client, alice_h, cid, "hello", "key-abc-123")
    assert first.status_code == 201 and retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]
    assert message_count(client, alice_h, cid) == 1
    assert counts(client, bob_h)["unread_messages"] == 1

    # a new key is a new message
    assert send_with_key(client, alice_h, cid, "hello", "key-abc-456").status_code == 201
    assert message_count(client, alice_h, cid) == 2


def test_same_key_with_different_payload_is_rejected(client, make_user):
    _, alice_h = make_user("alice")
    bob, _ = make_user("bob")
    carol, _ = make_user("carol")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    other_cid = start(client, alice_h, carol["id"]).json()["id"]

    send_with_key(client, alice_h, cid, "hello", "key-xyz-789")
    assert send_with_key(client, alice_h, cid, "different", "key-xyz-789").status_code == 409
    assert send_with_key(client, alice_h, other_cid, "hello", "key-xyz-789").status_code == 409
    assert message_count(client, alice_h, cid) == 1
    assert message_count(client, alice_h, other_cid) == 0


def test_keys_are_scoped_per_sender(client, make_user):
    _, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    assert send_with_key(client, alice_h, cid, "hi", "shared-key-1").status_code == 201
    assert send_with_key(client, bob_h, cid, "hi", "shared-key-1").status_code == 201
    assert message_count(client, alice_h, cid) == 2


def test_concurrent_retries_create_one_message(client, make_user):
    from concurrent.futures import ThreadPoolExecutor
    _, alice_h = make_user("alice")
    bob, _ = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda _: send_with_key(client, alice_h, cid, "once", "concurrent-key-1"), range(4)
        ))
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201]
    assert len({r.json()["id"] for r in results}) == 1
    assert message_count(client, alice_h, cid) == 1


def test_invalid_idempotency_key_and_no_key(client, make_user):
    _, alice_h = make_user("alice")
    bob, _ = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    assert send_with_key(client, alice_h, cid, "x", "short").status_code == 422
    assert send_with_key(client, alice_h, cid, "x", "bad key with spaces").status_code == 422
    # without a key, sends work as before (no dedupe)
    send(client, alice_h, cid, "same")
    send(client, alice_h, cid, "same")
    assert message_count(client, alice_h, cid) == 2


# ---------- ordering guarantees the client relies on ----------

def test_every_history_mode_returns_oldest_first(client, make_user):
    _, alice_h = make_user("alice")
    bob, _ = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    ids = [send(client, alice_h, cid, f"m{i}").json()["id"] for i in range(6)]
    assert ids == sorted(ids)

    latest = client.get(f"/conversations/{cid}/messages?limit=3", headers=alice_h).json()
    older = client.get(f"/conversations/{cid}/messages?limit=3&before_id={latest[0]['id']}", headers=alice_h).json()
    newer = client.get(f"/conversations/{cid}/messages?after_id={ids[1]}", headers=alice_h).json()
    for page in (latest, older, newer):
        assert [m["id"] for m in page] == sorted(m["id"] for m in page)
    # the pages join up with no gap and no overlap
    assert [m["id"] for m in older + latest] == ids
    assert [m["id"] for m in newer] == ids[2:]


def test_send_waits_for_the_conversation_lock(client, make_user):
    """Sends in one conversation are serialized, so messages become visible in id
    order and an after_id cursor can never skip a message that commits late."""
    import threading
    from sqlalchemy import text
    from app.core.database import engine

    _, alice_h = make_user("alice")
    bob, _ = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]

    result = {}
    with engine.connect() as conn:
        tx = conn.begin()
        conn.execute(text("SELECT id FROM conversations WHERE id = :c FOR UPDATE"), {"c": cid})
        worker = threading.Thread(target=lambda: result.setdefault("r", send(client, alice_h, cid, "after the lock")))
        worker.start()
        worker.join(timeout=2)
        assert worker.is_alive(), "send should wait while another transaction holds the conversation"
        tx.rollback()  # release the lock
    worker.join(timeout=15)
    assert result["r"].status_code == 201


def test_sender_echo_carries_the_key_recipient_copy_does_not(client, make_user):
    from tests.test_realtime import connect, token_of
    _, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    cid = start(client, alice_h, bob["id"]).json()["id"]
    alice_ws, alice_s = connect(client, token_of(alice_h))
    bob_ws, bob_s = connect(client, token_of(bob_h))
    try:
        send_with_key(client, alice_h, cid, "hi", "echo-key-123")
        assert alice_s.receive_json()["idempotency_key"] == "echo-key-123"
        assert "idempotency_key" not in bob_s.receive_json()
    finally:
        alice_ws.__exit__(None, None, None)
        bob_ws.__exit__(None, None, None)
