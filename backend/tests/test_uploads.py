"""D14 media uploads: validation, WebP re-encode, EXIF strip, UUID names, safe serving."""
import io
import os
import re

from PIL import Image

from tests.factories import create_trip, register

UUID_WEBP = re.compile(r"^/media/(avatars|covers)/[0-9a-f-]{36}\.webp$")


def _image(fmt="JPEG", size=(64, 48), exif=False):
    img = Image.new("RGB", size, (200, 30, 30))
    buf = io.BytesIO()
    kwargs = {}
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "SecretCameraMaker"   # Make
        ex[0x8825] = {2: (12.0, 34.0, 56.0)}  # GPSInfo
        kwargs["exif"] = ex.tobytes()
    img.save(buf, format=fmt, **kwargs)
    buf.seek(0)
    return buf


def _upload_avatar(client, buf, name):
    return client.upload("/api/v1/auth/avatar", data={"file": (buf, name)})


def test_valid_jpeg_png_webp(client, app):
    register(client)
    for fmt, name in (("JPEG", "a.jpg"), ("PNG", "b.png"), ("WEBP", "c.webp")):
        r = _upload_avatar(client, _image(fmt), name)
        assert r.status_code == 200, (fmt, r.get_json())
        url = r.get_json()["upload"]["url"]
        assert UUID_WEBP.match(url)
        served = client.get(url)
        assert served.status_code == 200 and served.mimetype == "image/webp"
        assert Image.open(io.BytesIO(served.data)).format == "WEBP"


def test_exif_stripped(client, app):
    register(client)
    r = _upload_avatar(client, _image(exif=True), "gps.jpg")
    data = client.get(r.get_json()["upload"]["url"]).data
    assert b"SecretCameraMaker" not in data
    assert not Image.open(io.BytesIO(data)).getexif()


def test_replacing_deletes_old_file(client, app):
    register(client)
    first = _upload_avatar(client, _image(), "a.jpg").get_json()["upload"]["url"]
    second = _upload_avatar(client, _image(), "b.jpg").get_json()["upload"]["url"]
    assert first != second
    root = app.config["UPLOAD_DIR"]
    assert not os.path.exists(os.path.join(root, first[len("/media/"):]))
    assert os.path.exists(os.path.join(root, second[len("/media/"):]))
    assert client.get(first).status_code == 404


def test_invalid_extension(client):
    register(client)
    r = _upload_avatar(client, _image(), "evil.gif")
    assert r.status_code == 415 and r.get_json()["error"]["code"] == "unsupported_media_type"


def test_not_an_image(client):
    register(client)
    r = _upload_avatar(client, io.BytesIO(b"<?php echo 'hi'; ?>" * 10), "shell.jpg")
    assert r.status_code == 415


def test_gif_disguised_as_png_rejected(client):
    register(client)
    r = _upload_avatar(client, _image("GIF"), "x.png")
    assert r.status_code == 415


def test_corrupted_image(client):
    register(client)
    data = _image().getvalue()[:200]
    r = _upload_avatar(client, io.BytesIO(data), "broken.jpg")
    assert r.status_code == 415


def test_oversized_upload(client):
    register(client)
    big = io.BytesIO(b"\xff\xd8" + os.urandom(2 * 1024 * 1024 + 10))
    r = _upload_avatar(client, big, "big.jpg")
    assert r.status_code == 413
    assert r.get_json()["error"]["code"] == "payload_too_large"


def test_cover_upload_and_ownership(client, make_client):
    register(client)
    tid = create_trip(client)["id"]
    r = client.upload(f"/api/v1/trips/{tid}/cover", data={"file": (_image("PNG", (3000, 1000)), "c.png")})
    assert r.status_code == 200
    url = r.get_json()["trip"]["cover_image_url"]
    assert url.startswith("/media/covers/")
    img = Image.open(io.BytesIO(client.get(url).data))
    assert max(img.size) <= 2000
    other = make_client()
    register(other)
    r2 = other.upload(f"/api/v1/trips/{tid}/cover", data={"file": (_image(), "c.jpg")})
    assert r2.status_code == 404


def test_path_traversal_blocked(client, app):
    for path in ("/media/../config.py", "/media/avatars/../../wsgi.py", "/media/%2e%2e/%2e%2e/etc/passwd",
                 "/media/avatars/notauuid.webp", "/media/other/123e4567-e89b-12d3-a456-426614174000.webp",
                 "/media/avatars/123e4567-e89b-12d3-a456-426614174000.webp"):
        r = client.get(path)
        assert r.status_code == 404, path


def test_upload_requires_auth(client):
    r = client.upload("/api/v1/auth/avatar", data={"file": (_image(), "a.jpg")})
    assert r.status_code == 401
