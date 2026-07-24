"""Attachments (images + videos, multi-file) and external reference links."""

import base64
from pathlib import Path
from typing import Any

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core import importers
from core.models import Issue, IssueMedia, friendly_link_label

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
    kinds = list(issue.media.values_list("kind", flat=True))
    assert kinds == [IssueMedia.Kind.IMAGE, IssueMedia.Kind.VIDEO]

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
    assert media.kind == IssueMedia.Kind.VIDEO


def test_friendly_link_label_falls_back_to_host() -> None:
    assert friendly_link_label("https://www.instagram.com/p/x/") == "Instagram"
    assert friendly_link_label("https://council.example.gov.my/x") == "council.example.gov.my"
