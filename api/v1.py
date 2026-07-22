"""
/api/v1 — the public API.

The OpenAPI schema generated from this module is a reviewed repo artifact
(api/openapi.json): regenerate with `manage.py export_openapi_schema`;
CI fails on unintended API surface changes. Additive changes anytime;
breaking changes only in a future /api/v2. See docs/DESIGN.md §7.
"""

from datetime import datetime

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Schema

from core.models import Issue

api_v1 = NinjaAPI(
    title="PleaseFix API",
    version="1.0.0",
    description="Public API for the PleaseFix civic issue tracker.",
)


class VersionOut(Schema):
    name: str
    api_version: str


class IssueOut(Schema):
    id: int
    title: str
    description: str
    status: str
    latitude: float
    longitude: float
    reporter_name: str
    created_at: datetime
    photos: list[str]


def _issue_out(issue: Issue) -> IssueOut:
    return IssueOut(
        id=issue.pk,
        title=issue.title,
        description=issue.description,
        status=issue.status,
        latitude=issue.latitude,
        longitude=issue.longitude,
        reporter_name=issue.reporter_name,
        created_at=issue.created_at,
        photos=[p.image.url for p in issue.photos.all()],
    )


@api_v1.get("/version", response=VersionOut, summary="API name and version")
def version(request: HttpRequest) -> VersionOut:
    return VersionOut(name="pleasefix", api_version="1.0.0")


@api_v1.get("/issues", response=list[IssueOut], summary="List issues (newest first)")
def list_issues(request: HttpRequest) -> list[IssueOut]:
    return [_issue_out(i) for i in Issue.objects.prefetch_related("photos")[:100]]


@api_v1.get("/issues/{issue_id}", response=IssueOut, summary="Get one issue")
def get_issue(request: HttpRequest, issue_id: int) -> IssueOut:
    return _issue_out(get_object_or_404(Issue.objects.prefetch_related("photos"), pk=issue_id))
