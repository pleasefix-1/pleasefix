from typing import Any
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import URLValidator
from django.db import IntegrityError, connection, transaction
from django.db.models import Prefetch
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from core import abuse, importers
from core.forms import ClaimForm, ImportForm, IssueForm, UpdateForm
from core.models import (
    Flag,
    Issue,
    IssueMedia,
    IssueReference,
    IssueUpdate,
    media_kind_for_name,
)

# Lazy so it renders in the viewer's language per-request, not once at import.
THROTTLE_MESSAGE = _("Too many submissions from your connection — please try again later.")

PUBLIC_UPDATES = Prefetch("updates", queryset=IssueUpdate.objects.public())


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


def about(request: HttpRequest) -> HttpResponse:
    """Interactive explainer: what PleaseFix is and why it exists."""
    return render(request, "about.html")


def site_page(request: HttpRequest, page: str) -> HttpResponse:
    """Serve the static outreach/onboarding pages (site/*.html — the
    landing page, contributor tracks, and the developer walkthrough)
    from the app, so /site/dev.html works out of the box on every
    deployment. The <slug> URL converter admits no dots or slashes, so
    only files directly inside site/ are reachable."""
    path = settings.BASE_DIR / "site" / f"{page}.html"
    if not path.is_file():
        raise Http404
    return HttpResponse(path.read_bytes(), content_type="text/html; charset=utf-8")


# A report can carry at most this many external links — enough for the
# source post plus a few corroborating articles, not a link farm.
MAX_LINKS = 10


def _attach_media(issue: Issue, uploads: list[Any], photo_url: str) -> None:
    """Store the reporter's own attachments (images/videos, already
    validated by the form). Only when they attached nothing do we fall
    back to the importer-carried photo URL (SSRF-guarded download)."""
    created = False
    for upload in uploads:
        kind = media_kind_for_name(getattr(upload, "name", "") or "")
        if kind is None:
            continue
        IssueMedia.objects.create(issue=issue, file=upload, kind=kind)
        created = True
    if not created and photo_url:
        downloaded = importers.download_photo(photo_url)
        if downloaded is not None:
            name, content = downloaded
            kind = media_kind_for_name(name) or IssueMedia.Kind.IMAGE
            IssueMedia.objects.create(issue=issue, file=ContentFile(content, name=name), kind=kind)


def _attach_references(issue: Issue, urls: list[str]) -> None:
    """Store user-supplied external links as reference chips. The imported
    source_url lives on the Issue itself and is rendered alongside these,
    so it is not duplicated here. Invalid/duplicate URLs are dropped."""
    validate = URLValidator(schemes=["http", "https"])
    seen: set[str] = set()
    refs: list[IssueReference] = []
    for raw in urls:
        url = (raw or "").strip()
        if not url or url in seen:
            continue
        try:
            validate(url)
        except ValidationError:
            continue
        seen.add(url)
        refs.append(IssueReference(issue=issue, url=url))
        if len(refs) >= MAX_LINKS:
            break
    IssueReference.objects.bulk_create(refs)


def report_new(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = IssueForm(request.POST, request.FILES)
        if form.is_valid():
            if form.is_spam:
                return redirect("issue_list")  # honeypot: pretend success
            if abuse.throttled(request, "report", abuse.throttle_limit("report")):
                form.add_error(None, THROTTLE_MESSAGE)
                return render(request, "issues/report_new.html", {"form": form})
            issue, claim_token = Issue.objects.create_report(
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                longitude=form.cleaned_data["longitude"],
                latitude=form.cleaned_data["latitude"],
                reporter_name=form.cleaned_data["reporter_name"],
                source_url=form.cleaned_data["source_url"],
                ip_hash=abuse.ip_hash(request),
                owner=request.user if request.user.is_authenticated else None,
            )
            _attach_media(issue, form.cleaned_data["attachments"], form.cleaned_data["photo_url"])
            _attach_references(issue, request.POST.getlist("link"))
            # Shown once on the issue page; never stored raw.
            request.session[f"claim_secret_{issue.public_id}"] = claim_token
            return redirect(issue)
    else:
        form = IssueForm(initial=_prefill_initial(request))
    return render(request, "issues/report_new.html", {"form": form})


# Fields the browser-side import (bookmarklet / PWA share-target) may
# prefill via GET query params. No server fetch happens here — values are
# just rendered into the form for the reporter to review; photo_url is
# only downloaded (SSRF-guarded) on submit.
_PREFILL_FIELDS = {"title": 200, "description": 5000, "source_url": 500, "photo_url": 500}


def _prefill_initial(request: HttpRequest) -> dict[str, str] | None:
    """Build the report form's initial data from a server-side import
    (session) or a browser-side import (GET query params, incl. the PWA
    share-target which maps shared title/text/url onto these names)."""
    initial: dict[str, str] = dict(request.session.pop("import_initial", None) or {})
    for field, limit in _PREFILL_FIELDS.items():
        value = request.GET.get(field, "").strip()
        if value:
            initial[field] = value[:limit]
    return initial or None


def _bookmarklet(request: HttpRequest) -> str:
    """A javascript: bookmarklet that scrapes the page the reporter is on
    (OpenGraph/title/first image) and opens the prefilled report form.
    Because it runs in the target page's own context, there's no CORS
    barrier and no server-side fetch — it works for Reddit/FB/X, on the
    reporter's own IP and login, where server-side import gets blocked."""
    report_url = request.build_absolute_uri(reverse("report_new"))
    js = (
        "(function(){"
        "function m(p){var e=document.querySelector("
        "'meta[property=\"'+p+'\"],meta[name=\"'+p+'\"]');return e?e.content:'';}"
        "var t=m('og:title')||document.title,"
        "d=m('og:description')||m('description')||'',"
        "i=m('og:image')||'',u=location.href;"
        "window.open('" + report_url + "?title='+encodeURIComponent(t)"
        "+'&description='+encodeURIComponent(d)"
        "+'&source_url='+encodeURIComponent(u)"
        "+'&photo_url='+encodeURIComponent(i));"
        "})();"
    )
    return "javascript:" + js


def report_import(request: HttpRequest) -> HttpResponse:
    """Prefill a report from a social-media / web link (see core.importers)."""
    context: dict[str, object] = {"bookmarklet": _bookmarklet(request)}
    warnings: list[str] = []
    if request.method == "POST":
        form = ImportForm(request.POST)
        if form.is_valid():
            try:
                if abuse.throttled(request, "import", abuse.throttle_limit("import")):
                    raise importers.ImportError_(str(THROTTLE_MESSAGE))
                candidate = importers.fetch_candidate(form.cleaned_data["url"])
            except importers.ImportError_ as exc:
                form.add_error("url", str(exc))
            else:
                description = candidate.description
                if candidate.author:
                    description += _("\n\n(Imported from a post by %(author)s)") % {
                        "author": candidate.author
                    }
                request.session["import_initial"] = {
                    "title": candidate.title[:200],
                    "description": description.strip(),
                    "source_url": candidate.source_url,
                    "photo_url": candidate.photo_url,
                }
                if not candidate.warnings:
                    return redirect("report_new")
                warnings.extend(candidate.warnings)
                context["proceed"] = True
    else:
        form = ImportForm()
    context["form"] = form
    context["warnings"] = warnings
    return render(request, "issues/report_import.html", context)


def issue_list(request: HttpRequest) -> HttpResponse:
    issues = Issue.objects.public().prefetch_related("media")[:100]
    return render(request, "issues/list.html", {"issues": issues})


def _detail_context(request: HttpRequest, issue: Issue, form: UpdateForm) -> dict[str, object]:
    share_url = request.build_absolute_uri(reverse("issue_shortlink", args=[issue.public_id]))
    share_text = f"{issue.title} ({issue.reference_code})"
    is_owner = request.user.is_authenticated and issue.owner_id == request.user.pk
    return {
        "issue": issue,
        "updates": issue.updates.filter(is_hidden=False),
        "update_form": form,
        "share_url": share_url,
        "share_text": share_text,
        "share_quoted": quote(f"{share_text} {share_url}"),
        "is_owner": is_owner,
        "can_claim": request.user.is_authenticated and not issue.is_claimed,
        "claim_form": ClaimForm(),
        # One-time banner right after reporting: the secret + login CTA.
        "new_claim_secret": request.session.pop(f"claim_secret_{issue.public_id}", None),
    }


def issue_detail(request: HttpRequest, public_id: str) -> HttpResponse:
    issue = get_object_or_404(
        Issue.objects.public().prefetch_related("media", "references", PUBLIC_UPDATES),
        public_id=public_id,
    )
    return render(request, "issues/detail.html", _detail_context(request, issue, UpdateForm()))


@require_POST
def update_new(request: HttpRequest, public_id: str) -> HttpResponse:
    """Follow-up by anyone — no login (see docs/ABUSE.md for the guards)."""
    issue = get_object_or_404(Issue.objects.public(), public_id=public_id)
    form = UpdateForm(request.POST, request.FILES)
    if form.is_valid():
        if form.is_spam:
            return redirect(issue)  # honeypot: pretend success
        if abuse.throttled(request, "update", abuse.throttle_limit("update")):
            messages.error(request, THROTTLE_MESSAGE)
            return redirect(issue)
        by_reporter = bool(request.user.is_authenticated and issue.owner_id == request.user.pk)
        secret = form.cleaned_data["reporter_secret"]
        if secret and not by_reporter:
            if issue.check_claim(secret):
                by_reporter = True
            else:
                form.add_error("reporter_secret", _("That secret doesn't match this report."))
                return render(request, "issues/detail.html", _detail_context(request, issue, form))
        IssueUpdate.objects.create(
            issue=issue,
            text=form.cleaned_data["text"],
            author_name=form.cleaned_data["author_name"],
            photo=form.cleaned_data["photo"] or "",
            by_reporter=by_reporter,
            ip_hash=abuse.ip_hash(request),
        )
        messages.success(request, _("Update added — thank you."))
        return redirect(issue)
    return render(request, "issues/detail.html", _detail_context(request, issue, form))


@require_POST
def issue_claim(request: HttpRequest, public_id: str) -> HttpResponse:
    """Attach an anonymous report to the logged-in account, proven by the
    reporter secret. Claimed reports earn a higher flag threshold."""
    issue = get_object_or_404(Issue.objects.public(), public_id=public_id)
    if not request.user.is_authenticated:
        return redirect_to_login(issue.get_absolute_url())
    if abuse.throttled(request, "claim", abuse.throttle_limit("claim")):
        messages.error(request, THROTTLE_MESSAGE)
        return redirect(issue)
    form = ClaimForm(request.POST)
    if form.is_valid() and not issue.is_claimed and issue.check_claim(form.cleaned_data["secret"]):
        issue.owner = request.user
        issue.save(update_fields=["owner"])
        messages.success(request, _("Report claimed — it's now linked to your account."))
    else:
        messages.error(request, _("That secret doesn't match this report."))
    return redirect(issue)


def _flag(
    request: HttpRequest, *, issue: Issue | None = None, update: IssueUpdate | None = None
) -> bool:
    """Record a flag (deduped per submitter). Returns False if throttled."""
    if abuse.throttled(request, "flag", abuse.throttle_limit("flag")):
        messages.error(request, THROTTLE_MESSAGE)
        return False
    try:
        with transaction.atomic():  # savepoint: a dup must not poison the request
            Flag.objects.create(ip_hash=abuse.ip_hash(request), issue=issue, update=update)
    except IntegrityError:
        pass  # same person flagging twice — counted once
    messages.success(request, _("Thanks — this has been reported for review by moderators."))
    return True


@require_POST
def issue_flag(request: HttpRequest, public_id: str) -> HttpResponse:
    issue = get_object_or_404(Issue.objects.public(), public_id=public_id)
    if _flag(request, issue=issue) and issue.maybe_auto_hide():
        return redirect("issue_list")
    return redirect(issue)


@require_POST
def update_flag(request: HttpRequest, update_id: int) -> HttpResponse:
    update = get_object_or_404(
        IssueUpdate.objects.filter(is_hidden=False).select_related("issue"), pk=update_id
    )
    _flag(request, update=update)
    update.maybe_auto_hide()
    return redirect(update.issue)


def issue_shortlink(request: HttpRequest, public_id: str) -> HttpResponse:
    """Short share URL: /i/<public_id> → the issue page."""
    issue = get_object_or_404(Issue.objects.public(), public_id=public_id)
    return redirect(issue, permanent=False)


def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness/readiness probe: process up + database reachable."""
    connection.ensure_connection()
    return JsonResponse({"status": "ok"})


def webmanifest(request: HttpRequest) -> JsonResponse:
    """PWA manifest. The share_target maps a shared post's title/text/url
    onto /report/'s prefill params, so on mobile 'Share → PleaseFix' opens
    the report form already filled (browser-side import; no server fetch)."""
    static = settings.STATIC_URL
    manifest = {
        "name": settings.SITE_NAME,
        "short_name": settings.SITE_NAME,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0b6e4f",
        "icons": [
            {"src": f"{static}icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {
                "src": f"{static}icons/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
        "share_target": {
            "action": reverse("report_new"),
            "method": "GET",
            "params": {"title": "title", "text": "description", "url": "source_url"},
        },
    }
    return JsonResponse(manifest, content_type="application/manifest+json")


# Minimal service worker: required for PWA installability (and thus the
# Android share-target). Network-passthrough; offline caching is a later
# enhancement.
_SERVICE_WORKER = """
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
"""


def service_worker(request: HttpRequest) -> HttpResponse:
    response = HttpResponse(_SERVICE_WORKER, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response
