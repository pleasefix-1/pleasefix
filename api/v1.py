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
from ninja import Field, NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.responses import Status

from core import abuse
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


class MediaOut(Schema):
    url: str
    kind: str  # "image" or "video"


class LinkOut(Schema):
    url: str
    label: str


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
    photos: list[str]  # image URLs only — kept for backward compatibility
    media: list[MediaOut]  # images and videos, in upload order
    links: list[LinkOut]  # external reference links (chips on the web UI)
    updates: list[UpdateOut]


class IssueCreateIn(Schema):
    title: str = Field(max_length=200)
    description: str = Field(max_length=5000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    reporter_name: str = Field("", max_length=100)
    source_url: str = Field("", max_length=500)


class IssueCreateOut(IssueOut):
    # Shown once, here in the response body — never stored raw or
    # retrievable again. See Issue.objects.create_report.
    claim_secret: str


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
        photos=[m.file.url for m in issue.media.all() if m.kind == "image"],
        media=[MediaOut(url=m.file.url, kind=m.kind) for m in issue.media.all()],
        links=[LinkOut(url=r.url, label=r.display_label) for r in issue.references.all()],
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
    qs = Issue.objects.public().prefetch_related("media", "references", _PUBLIC_UPDATES)
    return [_issue_out(i) for i in qs[:100]]


@api_v1.get("/issues/{issue_id}", response=IssueOut, summary="Get one issue by its public ID")
def get_issue(request: HttpRequest, issue_id: str) -> IssueOut:
    qs = Issue.objects.public().prefetch_related("media", "references", _PUBLIC_UPDATES)
    return _issue_out(get_object_or_404(qs, public_id=issue_id))


@api_v1.post("/issues", response={201: IssueCreateOut}, summary="Report a new issue")
def create_issue(request: HttpRequest, payload: IssueCreateIn) -> Status[IssueCreateOut]:
    # Same per-IP hourly limit as the web report form (core/abuse.py) —
    # one budget across channels, not one per channel.
    if abuse.throttled(request, "report", abuse.throttle_limit("report")):
        raise HttpError(429, "Too many reports from this connection — try again later.")
    issue, claim_secret = Issue.objects.create_report(
        title=payload.title,
        description=payload.description,
        longitude=payload.longitude,
        latitude=payload.latitude,
        reporter_name=payload.reporter_name,
        source_url=payload.source_url,
        ip_hash=abuse.ip_hash(request),
        source_channel=Issue.SourceChannel.API,
    )
    out = IssueCreateOut(**_issue_out(issue).model_dump(), claim_secret=claim_secret)
    return Status(201, out)
