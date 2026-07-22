from django.contrib.gis.geos import Point
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.forms import IssueForm
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
            )
            if form.cleaned_data["photo"]:
                IssuePhoto.objects.create(issue=issue, image=form.cleaned_data["photo"])
            return redirect(issue)
    else:
        form = IssueForm()
    return render(request, "issues/report_new.html", {"form": form})


def issue_list(request: HttpRequest) -> HttpResponse:
    issues = Issue.objects.prefetch_related("photos").all()[:100]
    return render(request, "issues/list.html", {"issues": issues})


def issue_detail(request: HttpRequest, pk: int) -> HttpResponse:
    issue = get_object_or_404(Issue.objects.prefetch_related("photos"), pk=pk)
    return render(request, "issues/detail.html", {"issue": issue})


def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness/readiness probe: process up + database reachable."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
