"""
Import an issue draft from a social-media / web URL.

Best-effort extraction: Reddit via its public JSON, X/Twitter via oEmbed,
Instagram via its public captioned-embed page, everything else (Facebook,
Threads, news sites, blogs) via OpenGraph meta tags. Platforms behind
login walls yield whatever their public preview exposes — the reporter
reviews and completes the draft either way (location, in particular,
almost never travels with a social post).
"""

import contextlib
import html
import ipaddress
import json
import re
import socket
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx
from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext as _

MAX_BYTES = 5 * 1024 * 1024
MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = 10.0
USER_AGENT = "PleaseFixBot/0.1 (+https://github.com/pleasefix-1/pleasefix; civic issue importer)"

_resolve_lock = threading.Lock()


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


def _resolve_validated(host: str, port: int) -> list[Any]:
    """Resolve `host` and reject unless EVERY returned address is a global
    (public) IP — this blocks private/loopback/link-local (incl. the cloud
    metadata endpoint) and multi-record answers that hide one internal IP."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ImportError_(_("That host could not be found.")) from exc
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ImportError_(_("That address is not reachable from here."))
    return infos


@contextlib.contextmanager
def _pinned_dns(host: str, infos: list[Any]) -> Iterator[None]:
    """Pin `host` to the already-validated addresses for the duration of a
    request, so httpx's own resolution can't be rebound to an internal IP
    between our check and its connect (DNS-rebinding / TOCTOU). Other hosts
    resolve normally. Serialized because it swaps a process-global."""
    original = socket.getaddrinfo

    def patched(h: Any, p: Any, *a: Any, **k: Any) -> list[Any]:
        if h == host:
            return infos
        return original(h, p, *a, **k)

    with _resolve_lock:
        socket.getaddrinfo = patched  # type: ignore[assignment]
        try:
            yield
        finally:
            socket.getaddrinfo = original


def safe_get(
    url: str, max_bytes: int = MAX_BYTES, headers: dict[str, str] | None = None
) -> httpx.Response:
    """GET an untrusted URL safely: http(s) only, DNS validated and pinned
    per hop against SSRF/rebinding, redirects followed manually with a
    re-check each hop, and the body streamed with a hard size cap so a
    malicious server can't exhaust memory before the limit is seen."""
    request_headers = {"User-Agent": USER_AGENT, "Accept-Language": "en, ms"}
    request_headers.update(headers or {})
    for _hop in range(MAX_REDIRECTS + 1):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ImportError_(_("Only http(s) links can be imported."))
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        infos = _resolve_validated(parsed.hostname, port)
        with (
            _pinned_dns(parsed.hostname, infos),
            httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client,
        ):
            with client.stream("GET", url, headers=request_headers) as response:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    if not location:
                        raise ImportError_(_("That link could not be followed."))
                    url = urljoin(url, location)
                    continue
                response.raise_for_status()
                total = 0
                chunks: list[bytes] = []
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ImportError_(_("That page is too large to import."))
                    chunks.append(chunk)
                response._content = b"".join(chunks)
                return response
    raise ImportError_(_("Too many redirects."))


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


def _reddit_token() -> str | None:
    """App-only OAuth token when credentials are configured — Reddit
    blocks unauthenticated requests from many server IP ranges, but the
    authenticated API works everywhere. Create a 'script' app at
    reddit.com/prefs/apps and set REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET."""
    client_id = getattr(settings, "REDDIT_CLIENT_ID", "")
    client_secret = getattr(settings, "REDDIT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return None
    token = cache.get("reddit_app_token")
    if isinstance(token, str):
        return token
    response = httpx.post(
        "https://www.reddit.com/api/v1/access_token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    token = str(response.json()["access_token"])
    cache.set("reddit_app_token", token, timeout=50 * 60)
    return token


def _import_reddit(url: str) -> ImportCandidate:
    token = _reddit_token()
    if token:
        match = re.search(r"/comments/([a-z0-9]+)", url)
        if not match:
            raise ImportError_(_("That doesn't look like a Reddit post link."))
        data = safe_get(
            f"https://oauth.reddit.com/comments/{match.group(1)}?raw_json=1&limit=1",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    else:
        api_url = url.split("?")[0].rstrip("/") + ".json"
        try:
            data = safe_get(api_url).json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                raise ImportError_(
                    _(
                        "Reddit blocks unauthenticated fetches from this server. "
                        "The site admin can enable Reddit imports by setting "
                        "REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET — or copy the post "
                        "details into the form manually."
                    )
                ) from exc
            raise
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


def _import_instagram(url: str) -> ImportCandidate:
    """Instagram post pages redirect server IPs to a login wall, but the
    captioned-embed page (what blogs iframe) is public: it carries the
    caption, the author handle, and the first photo — no API key needed."""
    match = re.search(r"instagram\.com/(?:[^/]+/)?(p|reel|tv)/([A-Za-z0-9_-]+)", url)
    if not match:
        raise ImportError_(_("That doesn't look like an Instagram post link."))
    kind, shortcode = match.groups()
    page = safe_get(f"https://www.instagram.com/{kind}/{shortcode}/embed/captioned/").text
    candidate = ImportCandidate(source_url=url)

    image_tag = re.search(r'<img[^>]+class="[^"]*EmbeddedMediaImage[^"]*"[^>]*>', page)
    if image_tag:
        src = re.search(r'src="([^"]+)"', image_tag.group(0))
        if src:
            candidate.photo_url = html.unescape(src.group(1))

    author = re.search(r'class="[^"]*CaptionUsername[^"]*"[^>]*>\s*(?:<[^>]+>\s*)*([^<]+)', page)
    if author:
        candidate.author = "@" + author.group(1).strip().lstrip("@")

    caption = re.search(r'<div class="Caption"[^>]*>(.*?)</div>', page, re.S)
    if caption:
        lines = [
            re.sub(r"\s+", " ", _strip_tags(line))
            for line in re.split(r"(?i)<br[^>]*>", caption.group(1))
        ]
        lines = [line for line in lines if line]
        # The embed repeats the author handle as the caption's first line.
        if lines and candidate.author and lines[0].lstrip("@") == candidate.author.lstrip("@"):
            lines = lines[1:]
        candidate.description = "\n".join(lines)
        if lines:
            candidate.title = lines[0][:120]

    if not candidate.title and not candidate.description and not candidate.photo_url:
        candidate.warnings.append(
            _(
                "Instagram didn't expose a public preview for that post (it may be "
                "private or removed) — please fill in the details yourself."
            )
        )
    return candidate


def _import_twitter(url: str) -> ImportCandidate:
    oembed = safe_get(f"https://publish.twitter.com/oembed?url={quote(url)}&omit_script=1").json()
    text = _strip_tags(oembed.get("html", ""))
    return ImportCandidate(
        source_url=url,
        title=text[:120],
        description=text,
        author=oembed.get("author_name", ""),
        warnings=[_("X/Twitter previews don't include photos — attach one if you have it.")],
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
            _(
                "That page didn't expose a public preview (it may require login) — "
                "please fill in the details yourself."
            )
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
        if host in ("instagram.com", "instagr.am") or host.endswith(".instagram.com"):
            return _import_instagram(url)
        return _import_opengraph(url)
    except ImportError_:
        raise
    except (httpx.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise ImportError_(_("Could not read that link — try filling the form manually.")) from exc


def download_photo(photo_url: str) -> tuple[str, bytes] | None:
    """Fetch a candidate photo; returns (filename, bytes) or None."""
    try:
        response = safe_get(photo_url, max_bytes=MAX_PHOTO_BYTES)
    except (ImportError_, httpx.HTTPError):
        return None
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    extension = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/pjpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type)
    if extension is None:
        # Fall back to the URL suffix; ImageField/Pillow validates on save.
        suffix = urlparse(photo_url).path.rsplit(".", 1)[-1].lower()
        extension = {
            "jpg": ".jpg",
            "jpeg": ".jpg",
            "png": ".png",
            "webp": ".webp",
            "gif": ".gif",
        }.get(suffix)
    if extension is None:
        return None
    return f"imported{extension}", response.content
