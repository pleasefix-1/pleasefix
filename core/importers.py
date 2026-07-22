"""
Import an issue draft from a social-media / web URL.

Best-effort extraction: Reddit via its public JSON, X/Twitter via oEmbed,
everything else (Facebook, Threads, news sites, blogs) via OpenGraph meta
tags. Platforms behind login walls yield whatever their public preview
exposes — the reporter reviews and completes the draft either way
(location, in particular, almost never travels with a social post).
"""

import html
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import quote, urlparse

import httpx

MAX_BYTES = 5 * 1024 * 1024
MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = 10.0
USER_AGENT = "PleaseFixBot/0.1 (+https://github.com/pleasefix-1/pleasefix; civic issue importer)"


class ImportError_(Exception):
    """Import failed in a way worth showing to the user."""


@dataclass
class ImportCandidate:
    source_url: str
    title: str = ""
    description: str = ""
    author: str = ""
    photo_url: str = ""
    warnings: list[str] = field(default_factory=list)


def _assert_public_http_url(url: str) -> None:
    """SSRF guard: http(s) only, and the host must not resolve to a
    private, loopback, or link-local address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ImportError_("Only http(s) links can be imported.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ImportError_("That host could not be found.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise ImportError_("That address is not reachable from here.")


def safe_get(url: str, max_bytes: int = MAX_BYTES) -> httpx.Response:
    """GET with an SSRF check on every redirect hop and a size cap."""
    for _ in range(MAX_REDIRECTS + 1):
        _assert_public_http_url(url)
        response = httpx.get(
            url,
            timeout=TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en, ms"},
        )
        if response.is_redirect:
            url = str(response.next_request.url) if response.next_request else ""
            continue
        response.raise_for_status()
        if len(response.content) > max_bytes:
            raise ImportError_("That page is too large to import.")
        return response
    raise ImportError_("Too many redirects.")


def _strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()


def _og_tags(page: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for match in re.finditer(
        r'<meta[^>]+(?:property|name)=["\'](og:[a-z:]+|twitter:[a-z:]+|description)["\']'
        r'[^>]+content=["\']([^"\']*)["\']',
        page,
        re.I,
    ):
        tags.setdefault(match.group(1).lower(), html.unescape(match.group(2)))
    # content-before-property attribute order variant
    for match in re.finditer(
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)='
        r'["\'](og:[a-z:]+|twitter:[a-z:]+|description)["\']',
        page,
        re.I,
    ):
        tags.setdefault(match.group(2).lower(), html.unescape(match.group(1)))
    return tags


def _import_reddit(url: str) -> ImportCandidate:
    api_url = url.split("?")[0].rstrip("/") + ".json"
    data = safe_get(api_url).json()
    post = data[0]["data"]["children"][0]["data"]
    candidate = ImportCandidate(
        source_url=url,
        title=post.get("title", ""),
        description=post.get("selftext", "").strip(),
        author=f"u/{post['author']}" if post.get("author") else "",
    )
    preview = post.get("preview", {}).get("images", [])
    if preview:
        candidate.photo_url = html.unescape(preview[0]["source"]["url"])
    elif str(post.get("url_overridden_by_dest", "")).endswith((".jpg", ".jpeg", ".png")):
        candidate.photo_url = post["url_overridden_by_dest"]
    return candidate


def _import_twitter(url: str) -> ImportCandidate:
    oembed = safe_get(f"https://publish.twitter.com/oembed?url={quote(url)}&omit_script=1").json()
    text = _strip_tags(oembed.get("html", ""))
    return ImportCandidate(
        source_url=url,
        title=text[:120],
        description=text,
        author=oembed.get("author_name", ""),
        warnings=["X/Twitter previews don't include photos — attach one if you have it."],
    )


def _import_opengraph(url: str) -> ImportCandidate:
    tags = _og_tags(safe_get(url).text)
    candidate = ImportCandidate(
        source_url=url,
        title=tags.get("og:title", ""),
        description=tags.get("og:description", tags.get("description", "")),
        photo_url=tags.get("og:image", ""),
    )
    if not candidate.title and not candidate.description:
        candidate.warnings.append(
            "That page didn't expose a public preview (it may require login) — "
            "please fill in the details yourself."
        )
    return candidate


def fetch_candidate(url: str) -> ImportCandidate:
    """Route to the right extractor by host; raises ImportError_ on failure."""
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    try:
        if host == "reddit.com" or host.endswith(".reddit.com"):
            return _import_reddit(url)
        if host in ("twitter.com", "x.com") or host.endswith((".twitter.com", ".x.com")):
            return _import_twitter(url)
        return _import_opengraph(url)
    except ImportError_:
        raise
    except (httpx.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise ImportError_("Could not read that link — try filling the form manually.") from exc


def download_photo(photo_url: str) -> tuple[str, bytes] | None:
    """Fetch a candidate photo; returns (filename, bytes) or None."""
    try:
        response = safe_get(photo_url, max_bytes=MAX_PHOTO_BYTES)
    except (ImportError_, httpx.HTTPError):
        return None
    content_type = response.headers.get("content-type", "").split(";")[0]
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(content_type)
    if extension is None:
        return None
    return f"imported{extension}", response.content
