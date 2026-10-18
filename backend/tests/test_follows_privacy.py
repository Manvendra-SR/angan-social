def create_post(client, headers, content="hello"):
    return client.post("/posts", data={"content": content}, headers=headers).json()


def test_private_account_requires_accepted_follow(client, make_user):
    alice, alice_h = make_user("alice", is_private=True)
    _, bob_h = make_user("bob")
    post = create_post(client, alice_h, "secret")

    # profile is visible, posts are not
    profile = client.get(f"/users/{alice['id']}", headers=bob_h).json()
    assert profile["can_view_posts"] is False and "email" not in profile
    assert client.get(f"/posts/{post['id']}", headers=bob_h).status_code == 403
    assert client.get(f"/users/{alice['id']}/posts", headers=bob_h).status_code == 403
    assert client.post(f"/likes/{post['id']}", headers=bob_h).status_code == 403
    assert client.get(f"/comments/posts/{post['id']}", headers=bob_h).status_code == 403
    assert client.get("/posts/feed", headers=bob_h).json() == []

    # follow request -> pending -> accepted
    assert client.post(f"/follows/{alice['id']}", headers=bob_h).json() == {"status": "pending"}
    assert client.get(f"/users/{alice['id']}", headers=bob_h).json()["follow_status"] == "pending"
    requests = client.get("/follows/requests", headers=alice_h).json()
    assert [r["follower_username"] for r in requests] == ["bob"]
    bob_id = requests[0]["follower_id"]
    assert client.post(f"/follows/{bob_id}/accept", headers=alice_h).status_code == 200

    assert client.get(f"/posts/{post['id']}", headers=bob_h).status_code == 200
    assert [p["content"] for p in client.get("/posts/feed", headers=bob_h).json()] == ["secret"]


def test_follow_public_account_and_unfollow(client, make_user):
    alice, _ = make_user("alice")
    _, bob_h = make_user("bob")
    assert client.post(f"/follows/{alice['id']}", headers=bob_h).json() == {"status": "accepted"}
    assert client.post(f"/follows/{alice['id']}", headers=bob_h).status_code == 400
    assert client.get(f"/users/{alice['id']}", headers=bob_h).json()["followers_count"] == 1
    assert client.delete(f"/follows/{alice['id']}", headers=bob_h).status_code == 204


def test_block_hides_posts_both_ways(client, make_user):
    alice, alice_h = make_user("alice")
    bob, bob_h = make_user("bob")
    a_post = create_post(client, alice_h, "from alice")
    b_post = create_post(client, bob_h, "from bob")
    client.post(f"/follows/{bob['id']}", headers=alice_h)

    assert client.post(f"/follows/{bob['id']}/block", headers=alice_h).status_code == 200

    assert client.get(f"/posts/{a_post['id']}", headers=bob_h).status_code == 403
    assert client.get(f"/posts/{b_post['id']}", headers=alice_h).status_code == 403
    assert client.get(f"/users/{alice['id']}", headers=bob_h).status_code == 403
    assert [p["content"] for p in client.get("/posts/feed", headers=alice_h).json()] == ["from alice"]
    # blocking removed alice's follow of bob
    assert client.get(f"/users/{alice['id']}", headers=alice_h).json()["following_count"] == 0
    assert client.post(f"/follows/{alice['id']}", headers=bob_h).status_code == 403

    assert client.delete(f"/follows/{bob['id']}/unblock", headers=alice_h).status_code == 204
    assert client.get(f"/posts/{b_post['id']}", headers=alice_h).status_code == 200


def test_block_invalid_targets(client, make_user):
    alice, alice_h = make_user("alice")
    assert client.post(f"/follows/{alice['id']}/block", headers=alice_h).status_code == 400
    assert client.post("/follows/9999/block", headers=alice_h).status_code == 404


def test_update_profile_and_search(client, make_user):
    _, alice_h = make_user("alice")
    make_user("bob")

    r = client.patch("/users/me", json={"bio": "hi there", "username": "alice_2"}, headers=alice_h)
    assert r.status_code == 200
    assert r.json()["bio"] == "hi there" and r.json()["username"] == "alice_2"
    assert client.patch("/users/me", json={"username": "BOB"}, headers=alice_h).status_code == 409
    assert client.patch("/users/me", json={"username": "x"}, headers=alice_h).status_code == 422

    found = client.get("/users/search?q=AL", headers=alice_h).json()
    assert [u["username"] for u in found] == ["alice_2"]
    # LIKE wildcards are treated literally
    assert client.get("/users/search?q=%25", headers=alice_h).json() == []
    assert client.get("/users/9999", headers=alice_h).status_code == 404
