"""POST /api/v1/issues — reporting an issue as an API client."""

import json
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client

from core.models import Issue

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    # Clear before (isolate from prior tests) and after (don't leak our
    # throttle counters into whichever module pytest collects next).
    cache.clear()
    yield
    cache.clear()


def report(client: Client, **overrides: Any) -> Any:
    payload = {
        "title": "Broken streetlight at Jalan 14/29",
        "description": "Dark stretch near the playground, out for two weeks.",
        "latitude": 3.0738,
        "longitude": 101.5183,
        "reporter_name": "Aina",
    }
    payload.update(overrides)
    return client.post("/api/v1/issues", data=json.dumps(payload), content_type="application/json")


def test_create_issue_via_api(client: Client) -> None:
    response = report(client)
    assert response.status_code == 201
    body = response.json()

    issue = Issue.objects.get()
    assert issue.title == "Broken streetlight at Jalan 14/29"
    assert issue.latitude == pytest.approx(3.0738)
    assert issue.longitude == pytest.approx(101.5183)
    assert issue.source_channel == Issue.SourceChannel.API

    assert body["id"] == issue.public_id
    assert body["title"] == issue.title
    assert body["claim_secret"]  # shown once, in the response body

    # It's also visible through the normal read API and web views.
    assert client.get(f"/api/v1/issues/{issue.public_id}").json()["id"] == issue.public_id


def test_create_issue_validates_location(client: Client) -> None:
    response = report(client, latitude=999)
    assert response.status_code == 422
    assert Issue.objects.count() == 0


def test_create_issue_rate_limited(client: Client) -> None:
    for i in range(5):
        assert report(client, title=f"Issue {i}").status_code == 201
    response = report(client, title="Issue 6")
    assert response.status_code == 429
    assert Issue.objects.count() == 5
