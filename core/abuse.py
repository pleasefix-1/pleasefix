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
    """The real client address.

    `X-Forwarded-For` is client-controlled and must NOT be trusted blindly
    — doing so lets one person forge unlimited distinct IPs and thereby
    bypass rate limits and flag-dedupe (flag-bombing any issue). We only
    consult it when `TRUSTED_PROXY_COUNT > 0` (set it to the number of
    proxies you actually run in front of the app, e.g. 1 for Caddy), and
    then read the entry that many hops from the right — the address the
    outermost trusted proxy saw. Otherwise we use REMOTE_ADDR only.
    """
    remote_addr = str(request.META.get("REMOTE_ADDR", ""))
    hops = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if hops > 0:
        forwarded = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))
        chain = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(chain) >= hops:
            return chain[-hops]
    return remote_addr


def ip_hash(request: HttpRequest) -> str:
    return hashlib.sha256(f"{settings.SECRET_KEY}:ip:{client_ip(request)}".encode()).hexdigest()


def throttled(request: HttpRequest, action: str, limit: int, window_seconds: int = 3600) -> bool:
    """True if this client already hit `limit` for `action` within the
    window. Fixed-window counter in the cache — coarse but effective.
    Fails CLOSED (treats as throttled) if the cache backend errors, so a
    dead cache can't silently disable every write limit."""
    key = f"throttle:{action}:{ip_hash(request)}"
    try:
        added = cache.add(key, 1, timeout=window_seconds)
        if added:
            return False
        try:
            count = int(cache.incr(key))
        except ValueError:  # expired between add and incr
            cache.add(key, 1, timeout=window_seconds)
            return False
        return count > limit
    except Exception:
        return True


def throttle_limit(action: str) -> int:
    """Per-action write limits per hour (settings.THROTTLE_LIMITS)."""
    return int(settings.THROTTLE_LIMITS[action])
