"""Attachments (images + videos, multi-file) and external reference links."""

import base64
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from core import importers
from core.models import Issue, Media, friendly_link_label

pytestmark = pytest.mark.django_db

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


@pytest.fixture(autouse=True)
def _isolate(settings: Any, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path
    cache.clear()  # reset per-IP throttle state between report POSTs


def _base(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Blocked drain overflowing",
        "description": "Water across the whole lane after every rain.",
        "latitude": "3.10",
        "longitude": "101.60",
        "reporter_name": "",
    }
    data.update(overrides)
    return data


def test_multiple_attachments_image_and_video(client: Client) -> None:
    response = client.post(
        "/report/",
        _base(
            attachments=[
                SimpleUploadedFile("a.png", TINY_PNG, content_type="image/png"),
                SimpleUploadedFile("clip.mp4", b"\x00\x00\x00\x18ftyp", content_type="video/mp4"),
            ]
        ),
    )
    assert response.status_code == 302
    issue = Issue.objects.get()
    kinds = list(issue.media.values_list("media__kind", flat=True))
    assert kinds == [Media.Kind.IMAGE, Media.Kind.VIDEO]

    detail = client.get(response["Location"])
    assert b"<video" in detail.content  # the clip renders as a player
    assert issue.first_image is not None  # og:image / thumbnail still work


def test_non_media_attachment_is_rejected(client: Client) -> None:
    response = client.post(
        "/report/",
        _base(attachments=SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")),
    )
    assert response.status_code == 200  # re-rendered with an error
    assert Issue.objects.count() == 0
    assert b"image or video" in response.content


def test_reference_links_are_stored_valid_only(client: Client) -> None:
    response = client.post(
        "/report/",
        _base(
            attachments="",
            link=[
                "https://www.instagram.com/p/abc123/",
                "not-a-url",
                "ftp://example.com/x",  # non-http(s) scheme dropped
                "https://www.thestar.com.my/news/story",
            ],
        ),
    )
    assert response.status_code == 302
    issue = Issue.objects.get()
    urls = list(issue.references.values_list("url", flat=True))
    assert urls == [
        "https://www.instagram.com/p/abc123/",
        "https://www.thestar.com.my/news/story",
    ]
    detail = client.get(response["Location"])
    assert b"Instagram" in detail.content  # friendly chip label


def test_imported_source_url_shows_as_a_chip(client: Client) -> None:
    response = client.post(
        "/report/",
        _base(attachments="", source_url="https://www.instagram.com/p/xyz/"),
    )
    assert response.status_code == 302
    issue = Issue.objects.get()
    assert issue.source_label == "Instagram"
    detail = client.get(response["Location"])
    assert b"View on Instagram" in detail.content


def test_imported_video_url_is_stored_as_video(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(importers, "download_photo", lambda url: ("imported.mp4", b"\x00ftyp"))
    response = client.post(
        "/report/",
        _base(attachments="", photo_url="https://example.com/clip.mp4"),
    )
    assert response.status_code == 302
    media = Issue.objects.get().media.get()
    assert media.kind == Media.Kind.VIDEO


def test_friendly_link_label_falls_back_to_host() -> None:
    assert friendly_link_label("https://www.instagram.com/p/x/") == "Instagram"
    assert friendly_link_label("https://council.example.gov.my/x") == "council.example.gov.my"


# --- phase 2: reusable media library -------------------------------------


def _upload(client: Client, name: str = "a.png") -> dict[str, Any]:
    resp = client.post(
        "/report/media/",
        {"file": SimpleUploadedFile(name, TINY_PNG, content_type="image/png")},
    )
    assert resp.status_code == 200, resp.content
    body: dict[str, Any] = resp.json()
    return body


def test_async_upload_creates_owned_media(client: Client) -> None:
    body = _upload(client)
    media = Media.objects.get(pk=body["id"])
    assert body["kind"] == "image"
    assert media.origin == Media.Origin.UPLOAD
    assert media.owner_token  # a stable token is stamped


def test_async_upload_rejects_non_media(client: Client) -> None:
    resp = client.post(
        "/report/media/",
        {"file": SimpleUploadedFile("x.txt", b"hi", content_type="text/plain")},
    )
    assert resp.status_code == 400
    assert Media.objects.count() == 0


def test_uploaded_media_can_be_reused_in_a_report(client: Client) -> None:
    body = _upload(client)
    data = _base(attachments="")
    data["media_id"] = str(body["id"])
    response = client.post("/report/", data)
    assert response.status_code == 302
    issue = Issue.objects.get()
    assert list(issue.media.values_list("media_id", flat=True)) == [body["id"]]


def test_cannot_attach_media_owned_by_another_session(client: Client) -> None:
    # Media owned by a *different* session — the IDOR guard must refuse it.
    other = Media.objects.create(
        file=ContentFile(TINY_PNG, name="o.png"),
        kind="image",
        owner_token="someone-else",  # noqa: S106
    )
    data = _base(attachments="")
    data["media_id"] = str(other.pk)
    response = client.post("/report/", data)
    assert response.status_code == 302
    assert Issue.objects.get().media.count() == 0  # not attached


def test_imported_media_has_dangling_ownership(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(importers, "download_photo", lambda url: ("imported.png", TINY_PNG))
    response = client.post(
        "/report/",
        _base(attachments="", photo_url="https://example.com/pothole.jpg"),
    )
    assert response.status_code == 302
    media = Issue.objects.get().media.get().media
    assert media.origin == Media.Origin.IMPORT
    assert media.uploaded_by_id is None and media.owner_token == ""


def test_cleanup_orphan_media_removes_only_old_unattached(client: Client) -> None:
    attached = _upload(client)
    data = _base(attachments="")
    data["media_id"] = str(attached["id"])
    client.post("/report/", data)

    orphan = Media.objects.create(file=ContentFile(TINY_PNG, name="orphan.png"), kind="image")
    Media.objects.filter(pk=orphan.pk).update(created_at=timezone.now() - timedelta(hours=48))
    fresh_orphan = Media.objects.create(file=ContentFile(TINY_PNG, name="fresh.png"), kind="image")

    call_command("cleanup_orphan_media", "--hours", "24")

    assert not Media.objects.filter(pk=orphan.pk).exists()  # old + unattached → gone
    assert Media.objects.filter(pk=fresh_orphan.pk).exists()  # too recent → kept
    assert Media.objects.filter(pk=attached["id"]).exists()  # attached → kept


# --- audit follow-up coverage --------------------------------------------


def test_size_caps_are_per_kind(client: Client) -> None:
    big = b"\x00" * (11 * 1024 * 1024)  # 11 MB: over the 10 MB image cap
    rejected = client.post(
        "/report/media/", {"file": SimpleUploadedFile("big.png", big, content_type="image/png")}
    )
    assert rejected.status_code == 400  # image cap enforced
    accepted = client.post(
        "/report/media/", {"file": SimpleUploadedFile("clip.mp4", big, content_type="video/mp4")}
    )
    assert accepted.status_code == 200  # 11 MB is fine for video (50 MB cap)


def test_duplicate_media_id_attaches_once(client: Client) -> None:
    body = _upload(client)
    data = _base(attachments="")
    data["media_id"] = [str(body["id"]), str(body["id"])]  # same id twice
    response = client.post("/report/", data)
    assert response.status_code == 302
    assert Issue.objects.get().media.count() == 1  # deduped, no IntegrityError


def test_combined_sources_order_and_skip_importer(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(importers, "download_photo", lambda url: ("imported.png", TINY_PNG))
    reused = _upload(client, name="reused.png")
    data = _base()
    data["attachments"] = SimpleUploadedFile("direct.png", TINY_PNG, content_type="image/png")
    data["media_id"] = str(reused["id"])
    data["photo_url"] = "https://example.com/x.jpg"  # must be skipped (other media present)
    response = client.post("/report/", data)
    assert response.status_code == 302
    issue = Issue.objects.get()
    assert issue.media.count() == 2  # reused + direct; importer photo skipped
    assert list(issue.media.values_list("order", flat=True)) == [0, 1]
    first = issue.media.first()
    assert first is not None
    assert first.media_id == reused["id"]  # reused attached first


def test_gallery_on_get_shows_only_owners_media(client: Client) -> None:
    body = _upload(client)
    mine = client.get("/report/")
    assert body["url"].encode() in mine.content  # owner sees it in the reuse gallery
    stranger = Client()
    assert body["url"].encode() not in stranger.get("/report/").content  # nobody else does


def test_logged_in_user_owns_and_reuses_their_uploads(
    client: Client, django_user_model: Any
) -> None:
    user = django_user_model.objects.create_user(username="rina", password="pw")  # noqa: S106
    client.force_login(user)
    body = _upload(client)
    assert Media.objects.get(pk=body["id"]).uploaded_by_id == user.pk
    data = _base(attachments="")
    data["media_id"] = str(body["id"])
    assert client.post("/report/", data).status_code == 302
    assert Issue.objects.get().media.count() == 1


def test_anonymous_upload_stays_owned_after_login(client: Client, django_user_model: Any) -> None:
    # The C-fix: ownership rides an owner_token in session data, which
    # survives login's session-key rotation — so a mid-report login does
    # not orphan an anonymous upload.
    body = _upload(client)  # anonymous
    user = django_user_model.objects.create_user(username="aziz", password="pw")  # noqa: S106
    client.force_login(user)  # cycles the session key, keeps session data
    data = _base(attachments="")
    data["media_id"] = str(body["id"])
    assert client.post("/report/", data).status_code == 302
    assert Issue.objects.get().media.count() == 1  # still attachable


def test_reference_links_capped_and_deduped(client: Client) -> None:
    links = [f"https://example.com/a{i}" for i in range(12)] + ["https://example.com/a0"]
    response = client.post("/report/", _base(attachments="", link=links))
    assert response.status_code == 302
    urls = list(Issue.objects.get().references.values_list("url", flat=True))
    assert len(urls) == 10  # MAX_LINKS
    assert len(set(urls)) == 10  # deduped


def test_api_exposes_media_and_links(client: Client) -> None:
    data = _base()
    data["attachments"] = [
        SimpleUploadedFile("a.png", TINY_PNG, content_type="image/png"),
        SimpleUploadedFile("clip.mp4", b"\x00ftyp", content_type="video/mp4"),
    ]
    data["link"] = "https://www.instagram.com/p/abc/"
    client.post("/report/", data)
    payload = client.get("/api/v1/issues").json()[0]
    kinds = sorted(m["kind"] for m in payload["media"])
    assert kinds == ["image", "video"]
    assert payload["photos"]  # images only, back-compat
    assert payload["links"][0]["label"] == "Instagram"
