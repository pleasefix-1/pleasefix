"""
Login-free abuse controls. Design notes in docs/ABUSE.md.

Three layers, cheapest first:
- honeypot form field (bots fill it; humans never see it) → silent drop
- per-IP rate throttles on every write endpoint (cache-backed)
- community flagging with per-IP dedupe → auto-hide at a threshold,
  pending human review (hide, never delete)

IPs are never stored raw: they are salted-hashed for dedupe/tracing,
which is enough to throttle, dedupe flags, and later ban — without
keeping PII (PDPA).
"""

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest


def client_ip(request: HttpRequest) -> str:
    # Behind Caddy (our compose topology) the client is the first
    # X-Forwarded-For entry; direct connections fall back to REMOTE_ADDR.
    forwarded = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))
    if forwarded:
        return forwarded.split(",")[0].strip()
    return str(request.META.get("REMOTE_ADDR", ""))


def ip_hash(request: HttpRequest) -> str:
    return hashlib.sha256(f"{settings.SECRET_KEY}:ip:{client_ip(request)}".encode()).hexdigest()


def throttled(request: HttpRequest, action: str, limit: int, window_seconds: int = 3600) -> bool:
    """True if this client already hit `limit` for `action` within the
    window. Fixed-window counter in the cache — coarse but effective."""
    key = f"throttle:{action}:{ip_hash(request)}"
    added = cache.add(key, 1, timeout=window_seconds)
    if added:
        return False
    try:
        count = int(cache.incr(key))
    except ValueError:  # expired between add and incr
        cache.add(key, 1, timeout=window_seconds)
        return False
    return count > limit
