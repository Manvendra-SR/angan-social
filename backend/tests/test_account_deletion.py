"""DELETE /users/me: what goes, what stays, and that the account is really gone."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import engine
from tests.conftest import JPEG, PNG
from tests.test_realtime import connect, token_of, close_code, ORIGIN

# every column that can point at a user
USER_REFERENCES = {
    "posts": ["user_id"],
    "comments": ["user_id"],
    "likes": ["user_id"],
    "follows": ["follower_id", "following_id"],
    "notifications": ["recipient_id", "actor_id"],
    "conversations": ["user_a_id", "user_b_id"],
    "messages": ["sender_id"],
    "conversation_reads": ["user_id"],
}


def rows_referencing(user_id: int) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            table: conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE " + " OR ".join(f"{c} = :u" for c in cols)), {"u": user_id}
            ).scalar()
            for table, cols in USER_REFERENCES.items()
        }


def image_post(client, headers, data, content="pic"):
    r = client.post("/posts", data={"content": content}, files={"image": ("a.jpg", data, "image/jpeg")}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def build_world(client, make_user):
    """alice interacts with bob in every possible way; bob and carol have their own stuff."""
    alice, alice_h = make_user("alice", is_private=True)
    bob, bob_h = make_user("bob")
    carol, carol_h = make_user("carol")

    alice_post = image_post(client, alice_h, JPEG, "alice's post")
    bob_post = image_post(client, bob_h, PNG, "bob's post")
    client.post(f"/likes/{bob_post['id']}", headers=alice_h)
    client.post(f"/comments/posts/{bob_post['id']}", json={"content": "from alice"}, headers=alice_h)
    client.post(f"/likes/{alice_post['id']}", headers=bob_h)  # bob -> notification for alice
    client.post(f"/follows/{bob['id']}", headers=alice_h)     # alice follows bob (notification for bob)
    client.post(f"/follows/{alice['id']}", headers=bob_h)     # pending request to private alice
    client.post(f"/follows/{carol['id']}/block", headers=alice_h)

    shared = client.post("/conversations", json={"user_id": bob["id"]}, headers=alice_h).json()["id"]
    m = client.post(f"/conversations/{shared}/messages", json={"body": "hi bob"}, headers=alice_h).json()
    client.post(f"/conversations/{shared}/messages", json={"body": "hi alice"}, headers=bob_h)
    client.post(f"/conversations/{shared}/read", json={"last_read_message_id": m["id"]}, headers=bob_h)

    unrelated = client.post("/conversations", json={"user_id": carol["id"]}, headers=bob_h).json()["id"]
    client.post(f"/conversations/{unrelated}/messages", json={"body": "bob to carol"}, headers=bob_h)
    return locals()


def test_requires_authentication(client):
    assert client.delete("/users/me").status_code == 401
    assert client.delete("/users/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_deletes_account_and_everything_it_owns(client, make_user, cloudinary_fake):
    w = build_world(client, make_user)
    alice, bob = w["alice"], w["bob"]
    assert any(rows_referencing(alice["id"]).values())

    assert client.delete("/users/me", headers=w["alice_h"]).status_code == 204

    assert rows_referencing(alice["id"]) == {t: 0 for t in USER_REFERENCES}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": alice["id"]}).scalar() == 0
        # rows under alice's post (bob's like + its notification) went with the post
        assert conn.execute(text("SELECT count(*) FROM likes WHERE post_id = :p"), {"p": w["alice_post"]["id"]}).scalar() == 0
    # alice's like/comment on bob's post are gone, the post itself stays
    post = client.get(f"/posts/{w['bob_post']['id']}", headers=w["bob_h"]).json()
    assert (post["likes_count"], post["comments_count"]) == (0, 0)
    assert client.get(f"/users/{bob['id']}", headers=w["bob_h"]).json()["followers_count"] == 0


def test_only_the_accounts_own_images_are_deleted(client, make_user, cloudinary_fake):
    w = build_world(client, make_user)
    alice_image, bob_image = cloudinary_fake.uploads  # upload order: alice's post, then bob's
    client.delete("/users/me", headers=w["alice_h"])
    assert cloudinary_fake.deleted == [alice_image]
    assert client.get(f"/posts/{w['bob_post']['id']}", headers=w["bob_h"]).json()["image_url"]


def test_shared_conversation_goes_other_users_stay_intact(client, make_user):
    w = build_world(client, make_user)
    bob_h, carol_h = w["bob_h"], w["carol_h"]
    client.delete("/users/me", headers=w["alice_h"])

    # the one-to-one conversation with alice can't exist without her
    assert client.get(f"/conversations/{w['shared']}/messages", headers=bob_h).status_code == 404
    # bob and carol are unaffected: accounts, posts, and their own conversation
    convs = client.get("/conversations", headers=bob_h).json()
    assert [c["id"] for c in convs] == [w["unrelated"]]
    assert [m["body"] for m in client.get(f"/conversations/{w['unrelated']}/messages", headers=carol_h).json()] == ["bob to carol"]
    assert client.get("/users/me", headers=bob_h).status_code == 200
    assert client.get("/users/me", headers=carol_h).status_code == 200
    # bob's badges no longer count anything from alice
    assert client.get("/users/me/counts", headers=bob_h).json() == {"unread_notifications": 0, "unread_messages": 0}
    # bob's only notifications were alice's (her follow), so his list is now empty
    assert client.get("/notifications", headers=bob_h).json() == []


def test_deleted_account_cannot_be_used_again(client, make_user):
    alice, alice_h = make_user("alice")
    client.delete("/users/me", headers=alice_h)

    # the old token is useless everywhere
    assert client.get("/users/me", headers=alice_h).status_code == 401
    assert client.post("/posts", data={"content": "ghost"}, headers=alice_h).status_code == 401
    assert client.delete("/users/me", headers=alice_h).status_code == 401
    with client.websocket_connect("/ws", headers=ORIGIN) as session:
        session.send_json({"type": "auth", "token": token_of(alice_h)})
        assert close_code(session) == 4401
    # the old credentials no longer log in
    r = client.post("/auth/login", data={"username": "alice@example.com", "password": "password123"})
    assert r.status_code == 401
    # the email and username are free again (a brand-new account, new id)
    again, _ = make_user("alice")
    assert again["id"] != alice["id"]


def test_open_sockets_are_closed_on_deletion(client, make_user):
    _, alice_h = make_user("alice")
    ws, session = connect(client, token_of(alice_h))
    client.delete("/users/me", headers=alice_h)
    assert close_code(session) == 4401
    ws.__exit__(None, None, None)


def test_failed_delete_changes_nothing(client, make_user, cloudinary_fake, monkeypatch):
    """If the transaction fails, the account and its images must all still be there."""
    alice, alice_h = make_user("alice")
    image_post(client, alice_h, JPEG)

    def broken_commit(self):
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(Session, "commit", broken_commit)
    with pytest.raises(OperationalError):
        client.delete("/users/me", headers=alice_h)
    monkeypatch.undo()

    assert cloudinary_fake.deleted == []
    assert client.get("/users/me", headers=alice_h).status_code == 200
    assert rows_referencing(alice["id"])["posts"] == 1
