"""End-to-end slice: report an issue with photo + location, then browse it."""

import base64
from pathlib import Path
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core.models import Issue

pytestmark = pytest.mark.django_db

# Smallest valid 1x1 PNG.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


@pytest.fixture(autouse=True)
def _media_tmp(settings: Any, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path


def report(client: Client, **overrides: Any) -> Any:
    data: dict[str, Any] = {
        "title": "Broken streetlight at Jalan 14/29",
        "description": "Dark stretch near the playground, out for two weeks.",
        "latitude": "3.0738",
        "longitude": "101.5183",
        "reporter_name": "Aina",
        "photo": SimpleUploadedFile("light.png", TINY_PNG, content_type="image/png"),
    }
    data.update(overrides)
    return client.post("/report/", data)


def test_full_flow_report_then_browse(client: Client) -> None:
    # Report form renders.
    assert client.get("/report/").status_code == 200

    # Submit with photo + location → redirect to the new issue.
    response = report(client)
    assert response.status_code == 302
    issue = Issue.objects.get()
    assert issue.latitude == pytest.approx(3.0738)
    assert issue.longitude == pytest.approx(101.5183)
    assert issue.status == Issue.Status.OPEN
    assert issue.photos.count() == 1

    # Detail page shows the report and its photo.
    detail = client.get(response.url)
    assert detail.status_code == 200
    assert b"Broken streetlight" in detail.content
    photo = issue.photos.first()
    assert photo is not None
    assert photo.image.url.encode() in detail.content

    # Browse list shows it too.
    listing = client.get("/issues/")
    assert b"Broken streetlight" in listing.content

    # And the public API serves it (by public ID, not the database pk).
    api = client.get("/api/v1/issues").json()
    assert len(api) == 1
    assert api[0]["title"].startswith("Broken streetlight")
    assert api[0]["latitude"] == pytest.approx(3.0738)
    assert api[0]["photos"]
    assert api[0]["id"] == issue.public_id
    assert api[0]["reference_code"] == f"PF-{issue.public_id}"
    assert client.get(f"/api/v1/issues/{issue.public_id}").json()["id"] == issue.public_id


def test_photo_is_optional_but_location_is_not(client: Client) -> None:
    assert report(client, photo="").status_code == 302
    response = report(client, latitude="")
    assert response.status_code == 200  # form redisplayed with errors
    assert Issue.objects.count() == 1


def test_malay_report_form(client: Client) -> None:
    response = client.get("/report/", HTTP_ACCEPT_LANGUAGE="ms")
    assert b"Laporkan isu" in response.content
