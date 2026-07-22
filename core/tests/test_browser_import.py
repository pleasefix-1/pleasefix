"""Browser-side import: GET prefill, bookmarklet, and PWA share-target."""

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_report_form_prefills_from_query_params(client: Client) -> None:
    response = client.get(
        "/report/",
        {
            "title": "Pothole on Jalan Ampang",
            "description": "Deep and dangerous.",
            "source_url": "https://www.reddit.com/r/malaysia/comments/abc/x/",
            "photo_url": "https://example.com/p.jpg",
        },
    )
    body = response.content.decode()
    assert 'value="Pothole on Jalan Ampang"' in body
    assert "Deep and dangerous." in body
    assert "reddit.com/r/malaysia" in body  # source_url hidden field
    assert "https://example.com/p.jpg" in body  # photo_url hidden field


def test_prefill_truncates_overlong_title(client: Client) -> None:
    response = client.get("/report/", {"title": "x" * 500})
    assert 'value="' + "x" * 200 + '"' in response.content.decode()
    assert "x" * 201 not in response.content.decode()


def test_manifest_declares_share_target(client: Client) -> None:
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/manifest+json"
    data = response.json()
    st = data["share_target"]
    assert st["action"] == "/report/"
    # Shared title/text/url map onto the report form's prefill params.
    assert st["params"] == {"title": "title", "text": "description", "url": "source_url"}
    assert data["icons"]


def test_service_worker_served_at_root_scope(client: Client) -> None:
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "javascript" in response["Content-Type"]
    assert response["Service-Worker-Allowed"] == "/"


def test_import_page_offers_bookmarklet(client: Client) -> None:
    body = client.get("/report/import/").content.decode()
    assert "javascript:" in body  # the draggable bookmarklet
    assert "og:title" in body  # its scraping logic
    assert "/report/?title=" in body  # deep-links into the prefill form


def test_shared_link_lands_prefilled(client: Client) -> None:
    """Simulates the PWA share-target GET: shared fields arrive as the
    report form's prefill params and render into the form."""
    response = client.get(
        "/report/",
        {
            "title": "Broken lift at LRT",
            "description": "Out for days",
            "source_url": "https://x.com/a/1",
        },
    )
    assert response.status_code == 200
    assert b"Broken lift at LRT" in response.content
