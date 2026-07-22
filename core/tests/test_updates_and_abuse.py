"""Follow-up updates by anyone + the login-free abuse guards."""

from pathlib import Path
from typing import Any

import pytest
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.test import Client

from core.models import Flag, Issue, IssueUpdate

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _isolate(settings: Any, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path
    cache.clear()


@pytest.fixture()
def issue() -> Issue:
    return Issue.objects.create(
        title="Tiang lampu condong di Jalan Besar",
        description="Leaning lamp post, looks about to fall.",
        location=Point(101.62, 3.11, srid=4326),
    )


def post_update(client: Client, issue: Issue, text: str = "Still leaning today.", **kw: Any) -> Any:
    data = {"text": text, "author_name": "Mei Ling", "website": ""}
    data.update(kw)
    return client.post(f"/issues/{issue.public_id}/update/", data)


def test_anyone_can_add_update(client: Client, issue: Issue) -> None:
    response = post_update(client, issue)
    assert response.status_code == 302
    page = client.get(issue.get_absolute_url()).content.decode()
    assert "Still leaning today." in page
    assert "Mei Ling" in page
    # and it's in the API
    api = client.get(f"/api/v1/issues/{issue.public_id}").json()
    assert api["updates"][0]["text"] == "Still leaning today."
    assert api["updates"][0]["author_name"] == "Mei Ling"


def test_honeypot_silently_drops_update(client: Client, issue: Issue) -> None:
    response = post_update(client, issue, website="http://spam.example")
    assert response.status_code == 302  # pretends success
    assert IssueUpdate.objects.count() == 0


def test_hidden_update_disappears_everywhere(client: Client, issue: Issue) -> None:
    update = IssueUpdate.objects.create(issue=issue, text="rude nonsense", is_hidden=True)
    page = client.get(issue.get_absolute_url()).content.decode()
    assert "rude nonsense" not in page
    assert client.get(f"/api/v1/issues/{issue.public_id}").json()["updates"] == []
    assert update in IssueUpdate.objects.all()  # hidden, not deleted


def test_update_rate_limit(client: Client, issue: Issue) -> None:
    for i in range(10):
        assert post_update(client, issue, text=f"update {i}").status_code == 302
    assert post_update(client, issue, text="update 11").status_code == 302
    assert IssueUpdate.objects.count() == 10  # 11th throttled


def test_flags_dedupe_and_auto_hide_issue(client: Client, issue: Issue) -> None:
    url = f"/issues/{issue.public_id}/flag/"
    # same connection flagging twice counts once
    client.post(url, REMOTE_ADDR="1.1.1.1")
    client.post(url, REMOTE_ADDR="1.1.1.1")
    issue.refresh_from_db()
    assert issue.flags.count() == 1 and not issue.is_hidden
    client.post(url, REMOTE_ADDR="2.2.2.2")
    client.post(url, REMOTE_ADDR="3.3.3.3")
    issue.refresh_from_db()
    assert issue.is_hidden
    # gone from every public surface, but not deleted
    assert client.get(issue.get_absolute_url()).status_code == 404
    assert client.get(f"/i/{issue.public_id}").status_code == 404
    assert client.get("/api/v1/issues").json() == []
    assert Issue.objects.filter(pk=issue.pk).exists()


def test_flag_auto_hides_update(client: Client, issue: Issue) -> None:
    update = IssueUpdate.objects.create(issue=issue, text="spam spam")
    for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        client.post(f"/updates/{update.pk}/flag/", REMOTE_ADDR=ip)
    update.refresh_from_db()
    assert update.is_hidden


def test_ip_stored_only_as_hash(client: Client, issue: Issue) -> None:
    post_update(client, issue)
    update = IssueUpdate.objects.get()
    assert update.ip_hash and "127.0.0.1" not in update.ip_hash
    assert len(update.ip_hash) == 64


def test_report_honeypot_and_flag_count(client: Client) -> None:
    response = client.post(
        "/report/",
        {
            "title": "spam",
            "description": "spam",
            "latitude": "3.1",
            "longitude": "101.6",
            "reporter_name": "",
            "website": "gotcha",
        },
    )
    assert response.status_code == 302
    assert Issue.objects.count() == 0
    assert Flag.objects.count() == 0
