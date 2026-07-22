"""
/api/v1 — the public API.

The OpenAPI schema generated from this module is a reviewed repo artifact
(api/openapi.json): regenerate with `manage.py export_openapi_schema`;
CI fails on unintended API surface changes. Additive changes anytime;
breaking changes only in a future /api/v2. See docs/DESIGN.md §7.
"""

from datetime import datetime

from django.db.models import Prefetch
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Schema

from core.models import Issue, IssueUpdate

# Only public (non-hidden) updates are serialized — filter at the DB, not
# in Python, so hidden rows are never fetched.
_PUBLIC_UPDATES = Prefetch("updates", queryset=IssueUpdate.objects.public())

api_v1 = NinjaAPI(
    title="PleaseFix API",
    version="1.0.0",
    description=(
        "Public API for the PleaseFix civic issue tracker. "
        "New here? The interactive developer walkthrough at /site/dev.html "
        "explains the architecture and data model; contributing starts at "
        "https://github.com/pleasefix-1/pleasefix/blob/main/CONTRIBUTING.md"
    ),
)


class VersionOut(Schema):
    name: str
    api_version: str


class UpdateOut(Schema):
    text: str
    author_name: str
    by_reporter: bool
    photo: str | None
    created_at: datetime


class IssueOut(Schema):
    id: str
    reference_code: str
    title: str
    description: str
    status: str
    latitude: float
    longitude: float
    reporter_name: str
    source_url: str
    is_claimed: bool
    created_at: datetime
    photos: list[str]
    updates: list[UpdateOut]


def _issue_out(issue: Issue) -> IssueOut:
    return IssueOut(
        id=issue.public_id,
        reference_code=issue.reference_code,
        title=issue.title,
        description=issue.description,
        status=issue.status,
        latitude=issue.latitude,
        longitude=issue.longitude,
        reporter_name=issue.reporter_name,
        source_url=issue.source_url,
        is_claimed=issue.is_claimed,
        created_at=issue.created_at,
        photos=[p.image.url for p in issue.photos.all()],
        updates=[
            UpdateOut(
                text=u.text,
                author_name=u.author_name,
                by_reporter=u.by_reporter,
                photo=u.photo.url if u.photo else None,
                created_at=u.created_at,
            )
            # `updates` is prefetched to the public() queryset by the views.
            for u in issue.updates.all()
        ],
    )


@api_v1.get("/version", response=VersionOut, summary="API name and version")
def version(request: HttpRequest) -> VersionOut:
    return VersionOut(name="pleasefix", api_version="1.0.0")


@api_v1.get("/issues", response=list[IssueOut], summary="List issues (newest first)")
def list_issues(request: HttpRequest) -> list[IssueOut]:
    qs = Issue.objects.public().prefetch_related("photos", _PUBLIC_UPDATES)
    return [_issue_out(i) for i in qs[:100]]


@api_v1.get("/issues/{issue_id}", response=IssueOut, summary="Get one issue by its public ID")
def get_issue(request: HttpRequest, issue_id: str) -> IssueOut:
    qs = Issue.objects.public().prefetch_related("photos", _PUBLIC_UPDATES)
    return _issue_out(get_object_or_404(qs, public_id=issue_id))
