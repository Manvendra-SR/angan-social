def create_post(client, headers, content="hello"):
    r = client.post("/posts", data={"content": content}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_get_post(client, make_user):
    alice, h = make_user("alice")
    post = create_post(client, h, "first post")
    assert post["author"] == {"id": alice["id"], "username": "alice"}
    assert post["likes_count"] == 0 and post["liked_by_me"] is False

    r = client.get(f"/posts/{post['id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["content"] == "first post"


def test_empty_post_rejected(client, make_user):
    _, h = make_user("alice")
    assert client.post("/posts", data={"content": "   "}, headers=h).status_code == 400
    assert client.post("/posts", headers=h).status_code == 400


def test_get_missing_post_and_invalid_id(client, make_user):
    _, h = make_user("alice")
    assert client.get("/posts/9999", headers=h).status_code == 404
    assert client.get("/posts/abc", headers=h).status_code == 422


def test_update_post_owner_only(client, make_user):
    _, alice = make_user("alice")
    _, bob = make_user("bob")
    post = create_post(client, alice)

    r = client.patch(f"/posts/{post['id']}", json={"content": "edited"}, headers=alice)
    assert r.status_code == 200 and r.json()["content"] == "edited"

    r = client.patch(f"/posts/{post['id']}", json={"content": "hacked"}, headers=bob)
    assert r.status_code == 403
    # text-only post can't have its text removed
    r = client.patch(f"/posts/{post['id']}", json={"content": None}, headers=alice)
    assert r.status_code == 400


def test_delete_post_owner_only(client, make_user):
    _, alice = make_user("alice")
    _, bob = make_user("bob")
    post = create_post(client, alice)

    assert client.delete(f"/posts/{post['id']}", headers=bob).status_code == 403
    assert client.delete(f"/posts/{post['id']}", headers=alice).status_code == 204
    assert client.get(f"/posts/{post['id']}", headers=alice).status_code == 404
    assert client.delete(f"/posts/{post['id']}", headers=alice).status_code == 404


def test_feed_pagination_newest_first(client, make_user):
    _, h = make_user("alice")
    for i in range(5):
        create_post(client, h, f"post {i}")

    page1 = client.get("/posts/feed?limit=2", headers=h).json()
    page2 = client.get("/posts/feed?limit=2&offset=2", headers=h).json()
    page3 = client.get("/posts/feed?limit=2&offset=4", headers=h).json()
    assert [p["content"] for p in page1] == ["post 4", "post 3"]
    assert [p["content"] for p in page2] == ["post 2", "post 1"]
    assert [p["content"] for p in page3] == ["post 0"]

    assert client.get("/posts/feed?limit=0", headers=h).status_code == 422
    assert client.get("/posts/feed?limit=1000", headers=h).status_code == 422


def test_feed_includes_own_private_posts(client, make_user):
    _, h = make_user("alice", is_private=True)
    create_post(client, h, "mine")
    assert [p["content"] for p in client.get("/posts/feed", headers=h).json()] == ["mine"]


def test_user_posts_listing(client, make_user):
    alice, h = make_user("alice")
    create_post(client, h, "a1")
    create_post(client, h, "a2")
    r = client.get(f"/users/{alice['id']}/posts?limit=1", headers=h)
    assert r.status_code == 200 and [p["content"] for p in r.json()] == ["a2"]
