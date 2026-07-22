"""Client-IP derivation and throttle behaviour (audit follow-up)."""

from typing import Any

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from core import abuse

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


def test_xff_ignored_when_no_trusted_proxies(settings: Any) -> None:
    settings.TRUSTED_PROXY_COUNT = 0
    request = RequestFactory().get(
        "/", REMOTE_ADDR="203.0.113.9", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8"
    )
    # Spoofed XFF must not change the identity — REMOTE_ADDR wins.
    assert abuse.client_ip(request) == "203.0.113.9"


def test_xff_used_at_configured_hop(settings: Any) -> None:
    settings.TRUSTED_PROXY_COUNT = 1
    request = RequestFactory().get(
        "/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="9.9.9.9, 10.0.0.2"
    )
    # One trusted proxy → the entry it appended is the rightmost.
    assert abuse.client_ip(request) == "10.0.0.2"


def test_spoofed_xff_cannot_forge_distinct_hashes(settings: Any) -> None:
    settings.TRUSTED_PROXY_COUNT = 0
    rf = RequestFactory()
    r1 = rf.get("/", REMOTE_ADDR="203.0.113.9", HTTP_X_FORWARDED_FOR="1.1.1.1")
    r2 = rf.get("/", REMOTE_ADDR="203.0.113.9", HTTP_X_FORWARDED_FOR="2.2.2.2")
    assert abuse.ip_hash(r1) == abuse.ip_hash(r2)  # same real client


def test_throttle_uses_settings_limit(settings: Any) -> None:
    settings.THROTTLE_LIMITS = {**settings.THROTTLE_LIMITS, "report": 2}
    request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.10")
    limit = abuse.throttle_limit("report")
    assert limit == 2
    assert not abuse.throttled(request, "report", limit)  # 1
    assert not abuse.throttled(request, "report", limit)  # 2
    assert abuse.throttled(request, "report", limit)  # 3 → blocked


def test_throttle_fails_closed_on_cache_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **k: object) -> None:
        raise RuntimeError("cache down")

    monkeypatch.setattr("core.abuse.cache.add", boom)
    request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.11")
    assert abuse.throttled(request, "report", 5) is True
