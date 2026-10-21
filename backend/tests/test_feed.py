"""Feed composition (discovery + privacy + blocks) and cursor pagination."""


def post(client, headers, content):
    r = client.post("/posts", data={"content": content}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def feed(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/posts/feed?{query}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def contents(posts):
    return [p["content"] for p in posts]


def test_feed_combines_own_followed_private_and_public_discovery(client, make_user):
    me, me_h = make_user("viewer")
    pub, pub_h = make_user("public_stranger")
    priv, priv_h = make_user("private_friend", is_private=True)
    _, other_priv_h = make_user("private_stranger", is_private=True)

    post(client, me_h, "mine")
    post(client, pub_h, "public, not followed")
    post(client, priv_h, "private, followed")
    post(client, other_priv_h, "private, not followed")

    # pending request: no access yet
    client.post(f"/follows/{priv['id']}", headers=me_h)
    assert "private, followed" not in contents(feed(client, me_h))

    client.post(f"/follows/{me['id']}/accept", headers=priv_h)
    got = contents(feed(client, me_h))
    assert set(got) == {"mine", "public, not followed", "private, followed"}


def test_followed_public_account_appears_once(client, make_user):
    _, me_h = make_user("viewer")
    pub, pub_h = make_user("pub")
    client.post(f"/follows/{pub['id']}", headers=me_h)  # qualifies as followed AND public
    post(client, pub_h, "only once")
    assert contents(feed(client, me_h)).count("only once") == 1


def test_blocks_exclude_posts_both_ways(client, make_user):
    me, me_h = make_user("viewer")
    a, a_h = make_user("blocked_by_me")
    _, b_h = make_user("blocks_me")
    post(client, a_h, "from a")
    post(client, b_h, "from b")
    client.post(f"/follows/{a['id']}/block", headers=me_h)
    client.post(f"/follows/{me['id']}/block", headers=b_h)
    assert contents(feed(client, me_h)) == []


def test_cursor_has_no_repeats_or_gaps_when_posts_are_inserted(client, make_user):
    _, h = make_user("viewer")
    ids = [post(client, h, f"p{i}")["id"] for i in range(5)]

    page1 = feed(client, h, limit=2)
    assert contents(page1) == ["p4", "p3"]

    post(client, h, "inserted after page 1")  # gets a higher id
    page2 = feed(client, h, limit=2, before_id=page1[-1]["id"])
    page3 = feed(client, h, limit=2, before_id=page2[-1]["id"])
    assert contents(page2) == ["p2", "p1"]
    assert contents(page3) == ["p0"]  # shorter than limit -> end of feed
    assert feed(client, h, limit=2, before_id=ids[0]) == []

    # a fresh load (refresh) starts from the newest post
    assert contents(feed(client, h, limit=1)) == ["inserted after page 1"]


def test_cursor_skips_nothing_when_a_post_is_deleted(client, make_user):
    _, h = make_user("viewer")
    for i in range(4):
        post(client, h, f"p{i}")
    page1 = feed(client, h, limit=2)
    p1 = [p for p in feed(client, h, limit=10) if p["content"] == "p1"][0]
    client.delete(f"/posts/{p1['id']}", headers=h)
    page2 = feed(client, h, limit=2, before_id=page1[-1]["id"])
    assert contents(page2) == ["p0"]


def test_user_posts_cursor_and_privacy(client, make_user):
    me, me_h = make_user("viewer")
    priv, priv_h = make_user("priv", is_private=True)
    for i in range(3):
        post(client, priv_h, f"x{i}")

    assert client.get(f"/users/{priv['id']}/posts", headers=me_h).status_code == 403
    page1 = client.get(f"/users/{priv['id']}/posts?limit=2", headers=priv_h).json()
    page2 = client.get(f"/users/{priv['id']}/posts?limit=2&before_id={page1[-1]['id']}", headers=priv_h).json()
    assert contents(page1) == ["x2", "x1"] and contents(page2) == ["x0"]


def test_feed_rejects_bad_cursor(client, make_user):
    _, h = make_user("viewer")
    assert client.get("/posts/feed?before_id=0", headers=h).status_code == 422
    assert client.get("/posts/feed?before_id=abc", headers=h).status_code == 422
