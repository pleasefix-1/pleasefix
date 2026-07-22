"""Reporter secrets: verified follow-ups and claiming reports into accounts."""

import re
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client

from core.models import Flag, Issue

pytestmark = pytest.mark.django_db

REPORT = {
    "title": "Papan tanda jalan hilang",
    "description": "Missing street sign at the junction.",
    "latitude": "3.12",
    "longitude": "101.63",
    "reporter_name": "Devi",
    "website": "",
}


@pytest.fixture(autouse=True)
def _isolate(settings: Any, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path
    cache.clear()


def report_and_get_secret(client: Client) -> tuple[Issue, str]:
    response = client.post("/report/", REPORT)
    issue = Issue.objects.latest("created_at")
    page = client.get(response["Location"]).content.decode()
    match = re.search(r"<code>([a-z0-9]+)</code>", page)
    assert match, "secret banner should appear once after reporting"
    return issue, match.group(1)


def test_secret_shown_exactly_once_and_only_hash_stored(client: Client) -> None:
    issue, secret = report_and_get_secret(client)
    assert issue.check_claim(secret)
    assert secret not in issue.claim_token_hash  # raw never stored
    second_view = client.get(issue.get_absolute_url()).content.decode()
    assert secret not in second_view  # one-time banner


def test_secret_verifies_follow_up(client: Client) -> None:
    issue, secret = report_and_get_secret(client)
    client.post(
        f"/issues/{issue.public_id}/update/",
        {
            "text": "Sign is still missing.",
            "author_name": "Devi",
            "website": "",
            "reporter_secret": secret,
        },
    )
    update = issue.updates.get()
    assert update.by_reporter
    page = client.get(issue.get_absolute_url()).content.decode()
    assert "original reporter" in page


def test_wrong_secret_is_rejected(client: Client) -> None:
    issue, _ = report_and_get_secret(client)
    response = client.post(
        f"/issues/{issue.public_id}/update/",
        {"text": "Fake claim.", "website": "", "reporter_secret": "wrongsecret1"},
    )
    assert response.status_code == 200  # redisplayed with error
    assert issue.updates.count() == 0


def test_claim_into_account_raises_flag_threshold(client: Client) -> None:
    issue, secret = report_and_get_secret(client)
    user = User.objects.create_user("devi", password="x")  # noqa: S106
    client.force_login(user)
    client.post(f"/issues/{issue.public_id}/claim/", {"secret": secret})
    issue.refresh_from_db()
    assert issue.owner == user
    assert issue.flag_threshold == Flag.CLAIMED_HIDE_THRESHOLD

    # 3 flags no longer hide a claimed report...
    anon = Client()
    for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        anon.post(f"/issues/{issue.public_id}/flag/", REMOTE_ADDR=ip)
    issue.refresh_from_db()
    assert not issue.is_hidden
    # ...5 do (still reviewable, still never deleted).
    for ip in ("4.4.4.4", "5.5.5.5"):
        anon.post(f"/issues/{issue.public_id}/flag/", REMOTE_ADDR=ip)
    issue.refresh_from_db()
    assert issue.is_hidden

    # API exposed the claim state while public.
    assert Issue.objects.filter(pk=issue.pk).exists()


def test_owner_updates_are_auto_verified(client: Client) -> None:
    issue, secret = report_and_get_secret(client)
    user = User.objects.create_user("devi2", password="x")  # noqa: S106
    client.force_login(user)
    client.post(f"/issues/{issue.public_id}/claim/", {"secret": secret})
    client.post(
        f"/issues/{issue.public_id}/update/",
        {"text": "Council replied to me by email.", "website": ""},
    )
    assert issue.updates.get().by_reporter


def test_claim_requires_login(client: Client) -> None:
    issue, secret = report_and_get_secret(client)
    response = client.post(f"/issues/{issue.public_id}/claim/", {"secret": secret})
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]
    issue.refresh_from_db()
    assert not issue.is_claimed


def test_logged_in_reporter_owns_immediately(client: Client) -> None:
    user = User.objects.create_user("chong", password="x")  # noqa: S106
    client.force_login(user)
    client.post("/report/", REPORT)
    issue = Issue.objects.get()
    assert issue.owner == user
