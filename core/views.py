from urllib.parse import quote

from django.contrib.gis.geos import Point
from django.core.files.base import ContentFile
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from core import importers
from core.forms import ImportForm, IssueForm
from core.models import Issue, IssuePhoto


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


def about(request: HttpRequest) -> HttpResponse:
    """Interactive explainer: what PleaseFix is and why it exists."""
    return render(request, "about.html")


def report_new(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = IssueForm(request.POST, request.FILES)
        if form.is_valid():
            issue = Issue.objects.create(
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                location=Point(
                    form.cleaned_data["longitude"], form.cleaned_data["latitude"], srid=4326
                ),
                reporter_name=form.cleaned_data["reporter_name"],
                source_url=form.cleaned_data["source_url"],
            )
            if form.cleaned_data["photo"]:
                IssuePhoto.objects.create(issue=issue, image=form.cleaned_data["photo"])
            elif form.cleaned_data["photo_url"]:
                downloaded = importers.download_photo(form.cleaned_data["photo_url"])
                if downloaded is not None:
                    name, content = downloaded
                    IssuePhoto.objects.create(issue=issue, image=ContentFile(content, name=name))
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
    issues = Issue.objects.prefetch_related("photos").all()[:100]
    return render(request, "issues/list.html", {"issues": issues})


def issue_detail(request: HttpRequest, public_id: str) -> HttpResponse:
    issue = get_object_or_404(Issue.objects.prefetch_related("photos"), public_id=public_id)
    share_url = request.build_absolute_uri(f"/i/{issue.public_id}")
    share_text = f"{issue.title} ({issue.reference_code})"
    return render(
        request,
        "issues/detail.html",
        {
            "issue": issue,
            "share_url": share_url,
            "share_text": share_text,
            "share_quoted": quote(f"{share_text} {share_url}"),
        },
    )


def issue_shortlink(request: HttpRequest, public_id: str) -> HttpResponse:
    """Short share URL: /i/<public_id> → the issue page."""
    issue = get_object_or_404(Issue, public_id=public_id)
    return redirect(issue, permanent=False)


def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness/readiness probe: process up + database reachable."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
