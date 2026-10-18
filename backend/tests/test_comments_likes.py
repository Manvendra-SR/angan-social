def create_post(client, headers, content="hello"):
    return client.post("/posts", data={"content": content}, headers=headers).json()


def test_comment_add_list_paginate(client, make_user):
    _, alice = make_user("alice")
    _, bob = make_user("bob")
    post = create_post(client, alice)

    for i in range(3):
        r = client.post(f"/comments/posts/{post['id']}", json={"content": f"c{i}"}, headers=bob)
        assert r.status_code == 201
    assert r.json()["author"]["username"] == "bob"

    all_comments = client.get(f"/comments/posts/{post['id']}", headers=alice).json()
    assert [c["content"] for c in all_comments] == ["c0", "c1", "c2"]  # oldest first
    page = client.get(f"/comments/posts/{post['id']}?limit=1&offset=1", headers=alice).json()
    assert [c["content"] for c in page] == ["c1"]

    assert client.get(f"/posts/{post['id']}", headers=alice).json()["comments_count"] == 3


def test_comment_validation_and_missing_post(client, make_user):
    _, h = make_user("alice")
    post = create_post(client, h)
    assert client.post(f"/comments/posts/{post['id']}", json={"content": "  "}, headers=h).status_code == 422
    assert client.post("/comments/posts/9999", json={"content": "hi"}, headers=h).status_code == 404
    assert client.get("/comments/posts/9999", headers=h).status_code == 404


def test_comment_edit_delete_owner_only(client, make_user):
    _, alice = make_user("alice")
    _, bob = make_user("bob")
    post = create_post(client, alice)
    comment = client.post(f"/comments/posts/{post['id']}", json={"content": "hi"}, headers=bob).json()

    assert client.patch(f"/comments/{comment['id']}", json={"content": "x"}, headers=alice).status_code == 403
    assert client.delete(f"/comments/{comment['id']}", headers=alice).status_code == 403

    r = client.patch(f"/comments/{comment['id']}", json={"content": "edited"}, headers=bob)
    assert r.status_code == 200 and r.json()["content"] == "edited"
    assert client.delete(f"/comments/{comment['id']}", headers=bob).status_code == 204
    assert client.delete(f"/comments/{comment['id']}", headers=bob).status_code == 404


def test_like_unlike_and_duplicate(client, make_user):
    _, alice = make_user("alice")
    _, bob = make_user("bob")
    post = create_post(client, alice)

    assert client.post(f"/likes/{post['id']}", headers=bob).status_code == 201
    assert client.post(f"/likes/{post['id']}", headers=bob).status_code == 409

    as_bob = client.get(f"/posts/{post['id']}", headers=bob).json()
    assert as_bob["likes_count"] == 1 and as_bob["liked_by_me"] is True
    assert client.get(f"/posts/{post['id']}", headers=alice).json()["liked_by_me"] is False

    assert client.delete(f"/likes/{post['id']}", headers=bob).status_code == 204
    assert client.get(f"/posts/{post['id']}", headers=bob).json()["likes_count"] == 0
    # unlike is idempotent
    assert client.delete(f"/likes/{post['id']}", headers=bob).status_code == 204


def test_like_missing_post(client, make_user):
    _, h = make_user("alice")
    assert client.post("/likes/9999", headers=h).status_code == 404


def test_deleting_post_removes_comments_and_likes(client, make_user):
    _, alice = make_user("alice")
    post = create_post(client, alice)
    client.post(f"/comments/posts/{post['id']}", json={"content": "hi"}, headers=alice)
    client.post(f"/likes/{post['id']}", headers=alice)
    assert client.delete(f"/posts/{post['id']}", headers=alice).status_code == 204
    assert client.get(f"/comments/posts/{post['id']}", headers=alice).status_code == 404
