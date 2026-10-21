"""Notification creation, dedupe, reversal behaviour, read state and counts."""


def post(client, headers, content="hello"):
    return client.post("/posts", data={"content": content}, headers=headers).json()


def notes(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/notifications?{query}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def counts(client, headers):
    return client.get("/users/me/counts", headers=headers).json()


def test_like_creates_one_notification_and_survives_unlike(client, make_user):
    alice, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    p = post(client, alice_h)

    client.post(f"/likes/{p['id']}", headers=bob_h)
    [n] = notes(client, alice_h)
    assert n["type"] == "like" and n["actor"]["username"] == "bob" and n["post_id"] == p["id"]
    assert n["is_read"] is False

    # duplicate like: 409 and no extra notification
    assert client.post(f"/likes/{p['id']}", headers=bob_h).status_code == 409
    # unlike keeps the history; like again doesn't duplicate it
    client.delete(f"/likes/{p['id']}", headers=bob_h)
    assert len(notes(client, alice_h)) == 1
    client.post(f"/likes/{p['id']}", headers=bob_h)
    assert len(notes(client, alice_h)) == 1
    assert notes(client, bob_h) == []


def test_no_notification_for_own_actions(client, make_user):
    _, h = make_user("alice")
    p = post(client, h)
    client.post(f"/likes/{p['id']}", headers=h)
    client.post(f"/comments/posts/{p['id']}", json={"content": "me"}, headers=h)
    assert notes(client, h) == []


def test_comment_notification_and_cascade_on_delete(client, make_user):
    _, alice_h = make_user("alice")
    _, bob_h = make_user("bob")
    p = post(client, alice_h)
    c = client.post(f"/comments/posts/{p['id']}", json={"content": "nice"}, headers=bob_h).json()

    [n] = notes(client, alice_h)
    assert n["type"] == "comment" and n["comment_id"] == c["id"] and n["post_id"] == p["id"]
    client.delete(f"/comments/{c['id']}", headers=bob_h)
    assert notes(client, alice_h) == []

    client.post(f"/comments/posts/{p['id']}", json={"content": "again"}, headers=bob_h)
    client.delete(f"/posts/{p['id']}", headers=alice_h)
    assert notes(client, alice_h) == []


def test_follow_public_account_and_unfollow_keeps_history(client, make_user):
    alice, alice_h = make_user("alice")
    _, bob_h = make_user("bob")
    client.post(f"/follows/{alice['id']}", headers=bob_h)
    [n] = notes(client, alice_h)
    assert n["type"] == "follow"

    client.delete(f"/follows/{alice['id']}", headers=bob_h)
    client.post(f"/follows/{alice['id']}", headers=bob_h)
    assert [x["type"] for x in notes(client, alice_h)] == ["follow"]


def test_follow_request_lifecycle(client, make_user):
    alice, alice_h = make_user("alice", is_private=True)
    bob, bob_h = make_user("bob")
    carol, carol_h = make_user("carol")

    client.post(f"/follows/{alice['id']}", headers=bob_h)
    client.post(f"/follows/{alice['id']}", headers=carol_h)
    assert sorted(n["type"] for n in notes(client, alice_h)) == ["follow_request", "follow_request"]

    # accept: the request notification goes, the requester is told
    client.post(f"/follows/{bob['id']}/accept", headers=alice_h)
    [bob_note] = notes(client, bob_h)
    assert bob_note["type"] == "follow_accepted" and bob_note["actor"]["id"] == alice["id"]

    # reject: request notification removed, nothing for the requester
    client.delete(f"/follows/{carol['id']}/reject", headers=alice_h)
    assert notes(client, alice_h) == []
    assert notes(client, carol_h) == []

    # cancel removes it too
    client.post(f"/follows/{alice['id']}", headers=carol_h)
    assert len(notes(client, alice_h)) == 1
    client.delete(f"/follows/{alice['id']}/cancel", headers=carol_h)
    assert notes(client, alice_h) == []


def test_going_public_accepts_pending_requests(client, make_user):
    alice, alice_h = make_user("alice", is_private=True)
    bob, bob_h = make_user("bob")
    p = post(client, alice_h, "secret")
    client.post(f"/follows/{alice['id']}", headers=bob_h)

    client.patch("/users/me", json={"is_private": False}, headers=alice_h)
    assert client.get(f"/users/{alice['id']}", headers=bob_h).json()["follow_status"] == "accepted"
    assert [n["type"] for n in notes(client, bob_h)] == ["follow_accepted"]
    assert notes(client, alice_h) == []
    assert client.get(f"/posts/{p['id']}", headers=bob_h).status_code == 200


def test_block_removes_notifications_both_ways(client, make_user):
    alice, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    client.post(f"/likes/{post(client, alice_h)['id']}", headers=bob_h)
    client.post(f"/likes/{post(client, bob_h)['id']}", headers=alice_h)
    client.post(f"/follows/{bob['id']}/block", headers=alice_h)
    assert notes(client, alice_h) == [] and notes(client, bob_h) == []


def test_list_cursor_read_state_and_counts(client, make_user):
    _, alice_h = make_user("alice")
    _, bob_h = make_user("bob")
    posts = [post(client, alice_h, f"p{i}") for i in range(3)]
    for p in posts:
        client.post(f"/likes/{p['id']}", headers=bob_h)

    assert counts(client, alice_h) == {"unread_notifications": 3, "unread_messages": 0}
    page1 = notes(client, alice_h, limit=2)
    page2 = notes(client, alice_h, limit=2, before_id=page1[-1]["id"])
    assert [n["post_id"] for n in page1 + page2] == [p["id"] for p in reversed(posts)]

    # listing alone never marks anything as read
    assert counts(client, alice_h)["unread_notifications"] == 3

    r = client.post(f"/notifications/{page1[0]['id']}/read", headers=alice_h)
    assert r.status_code == 200 and r.json()["unread_notifications"] == 2
    assert notes(client, alice_h, limit=1)[0]["is_read"] is True

    # someone else's notification looks like a missing one
    assert client.post(f"/notifications/{page1[1]['id']}/read", headers=bob_h).status_code == 404
    assert client.post("/notifications/999999/read", headers=alice_h).status_code == 404

    r = client.post("/notifications/read-all", headers=alice_h)
    assert r.json()["unread_notifications"] == 0
    assert all(n["is_read"] for n in notes(client, alice_h))


def test_notifications_require_auth(client):
    assert client.get("/notifications").status_code == 401
    assert client.get("/users/me/counts").status_code == 401
