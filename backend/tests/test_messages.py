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
