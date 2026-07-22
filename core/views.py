from urllib.parse import quote

from django.contrib import messages
from django.contrib.gis.geos import Point
from django.core.files.base import ContentFile
from django.db import IntegrityError, connection, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core import abuse, importers
from core.forms import ClaimForm, ImportForm, IssueForm, UpdateForm
from core.models import (
    Flag,
    Issue,
    IssuePhoto,
    IssueUpdate,
    generate_claim_token,
    hash_claim_token,
)

THROTTLE_MESSAGE = _("Too many submissions from your connection — please try again later.")


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


def about(request: HttpRequest) -> HttpResponse:
    """Interactive explainer: what PleaseFix is and why it exists."""
    return render(request, "about.html")


def report_new(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = IssueForm(request.POST, request.FILES)
        if form.is_valid():
            if form.is_spam:
                return redirect("issue_list")  # honeypot: pretend success
            if abuse.throttled(request, "report", limit=5):
                form.add_error(None, THROTTLE_MESSAGE)
                return render(request, "issues/report_new.html", {"form": form})
            claim_token = generate_claim_token()
            issue = Issue.objects.create(
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                location=Point(
                    form.cleaned_data["longitude"], form.cleaned_data["latitude"], srid=4326
                ),
                reporter_name=form.cleaned_data["reporter_name"],
                source_url=form.cleaned_data["source_url"],
                ip_hash=abuse.ip_hash(request),
                claim_token_hash=hash_claim_token(claim_token),
                owner=request.user if request.user.is_authenticated else None,
            )
            if form.cleaned_data["photo"]:
                IssuePhoto.objects.create(issue=issue, image=form.cleaned_data["photo"])
            elif form.cleaned_data["photo_url"]:
                downloaded = importers.download_photo(form.cleaned_data["photo_url"])
                if downloaded is not None:
                    name, content = downloaded
                    IssuePhoto.objects.create(issue=issue, image=ContentFile(content, name=name))
            # Shown once on the issue page; never stored raw.
            request.session[f"claim_secret_{issue.public_id}"] = claim_token
            return redirect(issue)
    else:
        form = IssueForm(initial=request.session.pop("import_initial", None))
    return render(request, "issues/report_new.html", {"form": form})


def report_import(request: HttpRequest) -> HttpResponse:
    """Prefill a report from a social-media / web link (see core.importers)."""
    context: dict[str, object] = {}
    warnings: list[str] = []
    if request.method == "POST":
        form = ImportForm(request.POST)
        if form.is_valid():
            try:
                if abuse.throttled(request, "import", limit=10):
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
    issues = Issue.public().prefetch_related("photos")[:100]
    return render(request, "issues/list.html", {"issues": issues})


def _detail_context(request: HttpRequest, issue: Issue, form: UpdateForm) -> dict[str, object]:
    share_url = request.build_absolute_uri(f"/i/{issue.public_id}")
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
    issue = get_object_or_404(Issue.public().prefetch_related("photos"), public_id=public_id)
    return render(request, "issues/detail.html", _detail_context(request, issue, UpdateForm()))


@require_POST
def update_new(request: HttpRequest, public_id: str) -> HttpResponse:
    """Follow-up by anyone — no login (see docs/ABUSE.md for the guards)."""
    issue = get_object_or_404(Issue.public(), public_id=public_id)
    form = UpdateForm(request.POST, request.FILES)
    if form.is_valid():
        if form.is_spam:
            return redirect(issue)  # honeypot: pretend success
        if abuse.throttled(request, "update", limit=10):
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
    issue = get_object_or_404(Issue.public(), public_id=public_id)
    if not request.user.is_authenticated:
        return redirect(f"/accounts/login/?next={issue.get_absolute_url()}")
    form = ClaimForm(request.POST)
    if form.is_valid() and not issue.is_claimed and issue.check_claim(form.cleaned_data["secret"]):
        issue.owner = request.user
        issue.save(update_fields=["owner"])
        messages.success(request, _("Report claimed — it's now linked to your account."))
    else:
        messages.error(request, _("That secret doesn't match this report."))
    return redirect(issue)


def _flag(request: HttpRequest, **target: object) -> None:
    if abuse.throttled(request, "flag", limit=30):
        messages.error(request, THROTTLE_MESSAGE)
        return
    try:
        with transaction.atomic():  # savepoint: a dup must not poison the request
            Flag.objects.create(ip_hash=abuse.ip_hash(request), **target)
    except IntegrityError:
        pass  # same person flagging twice — counted once
    messages.success(request, _("Thanks — this has been reported for review by moderators."))


@require_POST
def issue_flag(request: HttpRequest, public_id: str) -> HttpResponse:
    issue = get_object_or_404(Issue.public(), public_id=public_id)
    _flag(request, issue=issue)
    if issue.flags.count() >= issue.flag_threshold:
        issue.is_hidden = True
        issue.save(update_fields=["is_hidden"])
        return redirect("issue_list")
    return redirect(issue)


@require_POST
def update_flag(request: HttpRequest, update_id: int) -> HttpResponse:
    update = get_object_or_404(IssueUpdate.objects.filter(is_hidden=False), pk=update_id)
    threshold = Flag.CLAIMED_HIDE_THRESHOLD if update.by_reporter else Flag.AUTO_HIDE_THRESHOLD
    _flag(request, update=update)
    if update.flags.count() >= threshold:
        update.is_hidden = True
        update.save(update_fields=["is_hidden"])
    return redirect(update.issue)


def issue_shortlink(request: HttpRequest, public_id: str) -> HttpResponse:
    """Short share URL: /i/<public_id> → the issue page."""
    issue = get_object_or_404(Issue.public(), public_id=public_id)
    return redirect(issue, permanent=False)


def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness/readiness probe: process up + database reachable."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
