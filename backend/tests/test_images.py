import cloudinary.exceptions
from app.core import media
from tests.conftest import JPEG, PNG, WEBP


def upload(client, headers, data, filename="photo.jpg", content_type="image/jpeg", content=None):
    form = {"content": content} if content else {}
    return client.post(
        "/posts", data=form, files={"image": (filename, data, content_type)}, headers=headers
    )


def test_upload_valid_images(client, make_user, cloudinary_fake):
    _, h = make_user("alice")
    for data in (JPEG, PNG, WEBP):
        r = upload(client, h, data)
        assert r.status_code == 201, r.text
        assert r.json()["image_url"].startswith("https://res.cloudinary.com/")
    assert len(cloudinary_fake.uploads) == 3


def test_image_only_post_allowed(client, make_user):
    _, h = make_user("alice")
    r = upload(client, h, PNG)
    assert r.status_code == 201 and r.json()["content"] is None


def test_rejects_non_image_even_with_image_mime(client, make_user, cloudinary_fake):
    _, h = make_user("alice")
    r = upload(client, h, b"<?php echo 'hi'; ?>", filename="x.jpg", content_type="image/jpeg")
    assert r.status_code == 415
    r = upload(client, h, b"GIF89a" + b"\x00" * 50, filename="x.gif", content_type="image/gif")
    assert r.status_code == 415
    assert cloudinary_fake.uploads == []


def test_client_filename_and_mime_are_ignored(client, make_user, cloudinary_fake):
    _, h = make_user("alice")
    # a real PNG with a hostile name and wrong MIME type is accepted;
    # the stored name comes from Cloudinary, never from the client
    r = upload(client, h, PNG, filename="../../etc/passwd", content_type="text/plain")
    assert r.status_code == 201
    assert "passwd" not in r.json()["image_url"]


def test_rejects_oversized_and_empty(client, make_user, cloudinary_fake):
    _, h = make_user("alice")
    too_big = JPEG + b"\x00" * media.MAX_IMAGE_BYTES
    assert upload(client, h, too_big).status_code == 413
    assert upload(client, h, b"").status_code == 400
    assert cloudinary_fake.uploads == []


def test_cloudinary_failure_returns_502_and_saves_nothing(client, make_user, cloudinary_fake):
    _, h = make_user("alice")
    cloudinary_fake.fail_with = cloudinary.exceptions.Error("network down")
    r = upload(client, h, JPEG, content="with image")
    assert r.status_code == 502
    assert client.get("/posts/feed", headers=h).json() == []


def test_cloudinary_rejects_corrupt_image(client, make_user, cloudinary_fake):
    _, h = make_user("alice")
    cloudinary_fake.fail_with = cloudinary.exceptions.BadRequest("Invalid image file")
    assert upload(client, h, JPEG).status_code == 400


def test_replace_image_deletes_old_one(client, make_user, cloudinary_fake):
    _, alice = make_user("alice")
    _, bob = make_user("bob")
    post = upload(client, alice, JPEG).json()
    old_id = cloudinary_fake.uploads[0]

    r = client.put(f"/posts/{post['id']}/image", files={"image": ("b.png", PNG, "image/png")}, headers=bob)
    assert r.status_code == 403

    r = client.put(f"/posts/{post['id']}/image", files={"image": ("b.png", PNG, "image/png")}, headers=alice)
    assert r.status_code == 200
    assert r.json()["image_url"] != post["image_url"]
    assert cloudinary_fake.deleted == [old_id]


def test_delete_post_deletes_image(client, make_user, cloudinary_fake):
    _, h = make_user("alice")
    post = upload(client, h, JPEG).json()
    assert client.delete(f"/posts/{post['id']}", headers=h).status_code == 204
    assert cloudinary_fake.deleted == cloudinary_fake.uploads


def test_upload_requires_auth(client, cloudinary_fake):
    r = client.post("/posts", files={"image": ("a.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 401
    assert cloudinary_fake.uploads == []
