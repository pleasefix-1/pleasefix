"""Short IDs, share affordances, and the import-from-URL flow."""

import re
from pathlib import Path
from typing import Any

import pytest
from django.contrib.gis.geos import Point
from django.test import Client

from core import importers
from core.models import PUBLIC_ID_ALPHABET, Issue

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media_tmp(settings: Any, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture()
def issue() -> Issue:
    return Issue.objects.create(
        title="Pokok tumbang menghalang laluan",
        description="Fallen tree blocking the walkway.",
        location=Point(101.62, 3.11, srid=4326),
    )


def test_public_id_is_short_and_urlsafe(issue: Issue) -> None:
    assert len(issue.public_id) == 7
    assert all(c in PUBLIC_ID_ALPHABET for c in issue.public_id)
    assert issue.reference_code == f"PF-{issue.public_id}"
    assert issue.get_absolute_url() == f"/issues/{issue.public_id}/"


def test_shortlink_redirects(client: Client, issue: Issue) -> None:
    response = client.get(f"/i/{issue.public_id}")
    assert response.status_code == 302
    assert response["Location"] == f"/issues/{issue.public_id}/"


def test_detail_has_share_meta_and_buttons(client: Client, issue: Issue) -> None:
    content = client.get(issue.get_absolute_url()).content.decode()
    assert f'property="og:title" content="{issue.title} ({issue.reference_code})"' in content
    assert f"/i/{issue.public_id}" in content
    assert "wa.me/?text=" in content
    assert "twitter.com/intent/tweet" in content
    assert "facebook.com/sharer" in content
    assert 'id="copylink"' in content


def test_import_prefills_report_form(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(url: str) -> importers.ImportCandidate:
        return importers.ImportCandidate(
            source_url=url,
            title="Jalan berlubang besar di Kampung Baru",
            description="Deep pothole, three motorcyclists fell this week.",
            author="u/rakyatmarah",
            photo_url="https://example.com/pothole.jpg",
        )

    monkeypatch.setattr(importers, "fetch_candidate", fake_fetch)
    response = client.post(
        "/report/import/", {"url": "https://www.reddit.com/r/malaysia/comments/abc123/x/"}
    )
    assert response.status_code == 302 and response["Location"] == "/report/"
    form_page = client.get("/report/").content.decode()
    assert "Jalan berlubang besar" in form_page
    assert "u/rakyatmarah" in form_page
    assert "https://example.com/pothole.jpg" in form_page
    assert "reddit.com" in form_page  # prefilled-from notice


def test_import_failure_shows_error(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(url: str) -> importers.ImportCandidate:
        raise importers.ImportError_("Could not read that link.")

    monkeypatch.setattr(importers, "fetch_candidate", fail)
    response = client.post("/report/import/", {"url": "https://x.com/someone/status/1"})
    assert response.status_code == 200
    assert b"Could not read that link." in response.content


def test_submitting_imported_form_downloads_photo(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(importers, "download_photo", lambda url: ("imported.png", b"\x89PNG fake"))
    response = client.post(
        "/report/",
        {
            "title": "Imported pothole",
            "description": "From a reddit post.",
            "latitude": "3.15",
            "longitude": "101.7",
            "reporter_name": "",
            "source_url": "https://www.reddit.com/r/malaysia/comments/abc123/x/",
            "photo_url": "https://example.com/pothole.jpg",
        },
    )
    assert response.status_code == 302
    created = Issue.objects.get(title="Imported pothole")
    assert created.source_url.startswith("https://www.reddit.com/")
    assert created.photos.count() == 1


def test_ssrf_guard_rejects_non_http_scheme() -> None:
    with pytest.raises(importers.ImportError_):
        importers.safe_get("ftp://example.com/x")


def test_ssrf_guard_rejects_private_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def resolve_private(host: str, port: int, **kw: object) -> list[object]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve_private)
    with pytest.raises(importers.ImportError_):
        importers.safe_get("http://evil.example/")


def test_ssrf_guard_rejects_mixed_public_private(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def resolve_mixed(host: str, port: int, **kw: object) -> list[object]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", resolve_mixed)
    with pytest.raises(importers.ImportError_):
        importers.safe_get("http://rebind.example/")


def test_og_tag_parsing() -> None:
    page = """<html><head>
      <meta property="og:title" content="Longkang penuh sampah &amp; berbau" />
      <meta content="Residents complain." property="og:description"/>
      <meta property="og:image" content="https://cdn.example.com/p.jpg">
    </head></html>"""
    tags = importers._og_tags(page)
    assert tags["og:title"] == "Longkang penuh sampah & berbau"
    assert tags["og:description"] == "Residents complain."
    assert re.match(r"https://cdn", tags["og:image"])
