import hashlib
import secrets
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.gis.db import models as gis
from django.contrib.gis.geos import Point
from django.db import IntegrityError, models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

# Unambiguous lowercase alphabet (no 0/1/i/l/o) for short public IDs.
PUBLIC_ID_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"


def generate_public_id() -> str:
    """Short, random, stable issue ID, e.g. 'k7xq2mv' — used in URLs and
    as the human reference code ("PF-k7xq2mv"). 31^7 ≈ 2.7e10 values, so
    random collisions are vanishingly rare; uniqueness is DB-enforced."""
    return "".join(secrets.choice(PUBLIC_ID_ALPHABET) for _ in range(7))


def generate_claim_token() -> str:
    """The reporter's secret, shown once at submission: proves 'I am the
    original reporter' on follow-ups, and claims the report into an
    account later (progressive identity — the report comes first)."""
    return "".join(secrets.choice(PUBLIC_ID_ALPHABET) for _ in range(12))


def hash_claim_token(raw: str) -> str:
    """Only the salted hash is stored — a database leak must not leak
    everyone's reporter secrets."""
    return hashlib.sha256(f"{settings.SECRET_KEY}:claim:{raw.strip()}".encode()).hexdigest()


class Flaggable(models.Model):
    """Shared moderation behaviour for content anyone can flag."""

    is_hidden = models.BooleanField(default=False)

    class Meta:
        abstract = True

    @property
    def flag_threshold(self) -> int:
        raise NotImplementedError

    def maybe_auto_hide(self) -> bool:
        """Hide (never delete) once enough distinct submitters flag it.
        Returns True if this call crossed the threshold."""
        if not self.is_hidden and self.flags.count() >= self.flag_threshold:  # type: ignore[attr-defined]
            self.is_hidden = True
            self.save(update_fields=["is_hidden"])
            return True
        return False


# ---------------------------------------------------------------------------
# Routing: areas, bodies, categories (docs/DESIGN.md §6; jurisdictions are
# data, editable in admin — never code).
# ---------------------------------------------------------------------------


class Area(models.Model):
    """
    An administrative boundary (state, district, local-council area).
    Point → areas → bodies is how reports find their agencies. Boundaries
    get redrawn: redraws create new rows with a bumped generation and
    deactivate the old ones, so historical issues keep their snapshot.
    """

    class Kind(models.TextChoices):
        STATE = "state", _("State")
        DISTRICT = "district", _("District")
        COUNCIL = "council", _("Local council area")
        OTHER = "other", _("Other")

    name = models.CharField(_("name"), max_length=100)
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices, default=Kind.COUNCIL)
    # Geometry (not geography): point-in-polygon `covers` lookups on 4326.
    boundary = gis.MultiPolygonField(_("boundary"), srid=4326)
    external_code = models.CharField(_("external code"), max_length=30, blank=True)
    generation = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Body(models.Model):
    """
    An agency/authority reports get filed with (PBT, JKR, TNB, Prasarana…).
    Dispatch details beyond the email floor live on adapters, not here.
    """

    name = models.CharField(_("name"), max_length=150, unique=True)
    slug = models.SlugField(unique=True)
    # The email dispatch floor (docs/DESIGN.md §6). Overridable per category.
    dispatch_email = models.EmailField(_("dispatch email"), blank=True)
    homepage = models.URLField(_("homepage"), blank=True)
    notes = models.TextField(_("notes"), blank=True)
    areas = models.ManyToManyField(Area, blank=True, related_name="bodies")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "bodies"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CategoryGroup(models.Model):
    """Two-level category dropdown: Malaysian PBT taxonomies are large."""

    name = models.CharField(_("name"), max_length=100, unique=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name


class CategoryQuerySet(models.QuerySet["Category"]):
    def active(self) -> "CategoryQuerySet":
        return self.filter(state=Category.State.CONFIRMED, body__is_active=True)

    def for_point(self, point: Point) -> "CategoryQuerySet":
        """Categories a reporter at `point` can choose: the union across
        every active body whose area covers the point. Multi-body overlap
        (PBT + JKR + TNB) is the normal case, not an edge."""
        return self.active().filter(
            body__areas__is_active=True, body__areas__boundary__covers=point
        )


class Category(models.Model):
    """
    A per-body contact/category join — NOT a global taxonomy. Unique on
    (body, name); the report form shows the union of categories from all
    bodies covering the point, merged by name. Categories route to
    agencies; free-form tags (below) serve discovery/advocacy.
    """

    class State(models.TextChoices):
        CONFIRMED = "confirmed", _("Confirmed")
        # Unverified destinations hold dispatch; soft-delete only —
        # existing issues keep their category row forever.
        UNCONFIRMED = "unconfirmed", _("Unconfirmed")
        INACTIVE = "inactive", _("Inactive")

    body = models.ForeignKey(Body, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(_("name"), max_length=100)
    group = models.ForeignKey(
        CategoryGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name="categories"
    )
    state = models.CharField(max_length=12, choices=State.choices, default=State.UNCONFIRMED)
    # Overrides the body's dispatch email when set (one PBT: rubbish by
    # email, roads via SISPAA — adapter binding is two-level).
    dispatch_email = models.EmailField(_("dispatch email override"), blank=True)
    photo_required = models.BooleanField(default=False)
    # Dispatched but never public (plate numbers, welfare, salah laku).
    non_public = models.BooleanField(default=False)
    prefer_if_multiple = models.BooleanField(default=False)
    # SISPAA taxonomy mapping (kelewatan tindakan, kekurangan kemudahan…).
    sispaa_category = models.CharField(max_length=100, blank=True)
    # Category-defined extra questions: a small typed field schema
    # ({name, label, datatype, required, options…}); answers land on
    # Issue.extra_answers. Form machinery comes with the report flow.
    extra_fields = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["body", "name"], name="unique_category_per_body")
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.body.name})"


class Tag(models.Model):
    """Free-form community tag (a11y, CEDAW, public-transport…) — the
    advocacy/discovery axis, deliberately separate from routed categories."""

    name = models.SlugField(_("name"), max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class IssueQuerySet(models.QuerySet["Issue"]):
    def public(self) -> "IssueQuerySet":
        """Everything shown to the world goes through this: hidden
        (moderated), unconfirmed, and non-public issues never appear in
        lists, maps, or the API."""
        return self.filter(is_hidden=False, non_public=False, confirmed_at__isnull=False)


class IssueManager(models.Manager["Issue"]):
    def get_queryset(self) -> IssueQuerySet:
        return IssueQuerySet(self.model, using=self._db)

    def public(self) -> IssueQuerySet:
        return self.get_queryset().public()

    def create_report(
        self,
        *,
        title: str,
        description: str,
        longitude: float,
        latitude: float,
        reporter_name: str = "",
        source_url: str = "",
        ip_hash: str = "",
        owner: "AbstractBaseUser | None" = None,
        category: "Category | None" = None,
        anonymous: bool = False,
        source_channel: str = "",
        language: str = "",
        address: str = "",
    ) -> tuple["Issue", str]:
        """Create an issue and return (issue, raw_claim_token). The raw
        token is shown once and never stored; retries on the astronomically
        rare public_id collision instead of 500-ing. Snapshots the areas
        covering the point (matched-area drift must not rewrite history)."""
        claim_token = generate_claim_token()
        location = Point(longitude, latitude, srid=4326)
        for _attempt in range(5):
            try:
                issue = self.create(
                    title=title,
                    description=description,
                    location=location,
                    reporter_name=reporter_name,
                    source_url=source_url,
                    ip_hash=ip_hash,
                    owner_id=owner.pk if owner is not None else None,
                    claim_token_hash=hash_claim_token(claim_token),
                    category=category,
                    anonymous=anonymous,
                    source_channel=source_channel or Issue.SourceChannel.WEB,
                    language=language,
                    address=address,
                    non_public=category.non_public if category is not None else False,
                )
                issue.areas.set(Area.objects.filter(is_active=True, boundary__covers=location))
                return issue, claim_token
            except IntegrityError:
                continue  # public_id collision — regenerate via default
        raise IntegrityError("could not allocate a unique public_id")


class Issue(Flaggable):
    """
    A community issue — the community's record, not any agency's ticket.
    Its lifecycle (status) belongs to the platform; each official filing
    is a separate Filing row, and an agency closing its ticket never
    auto-closes the issue. Status types are a small closed set in code
    (invariants run on them); closure reason and fix provenance qualify
    them.
    """

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        FIXED = "fixed", _("Fixed")
        CLOSED = "closed", _("Closed")

    class ClosureReason(models.TextChoices):
        NOT_RESPONSIBLE = "not_responsible", _("No responsible agency")
        DUPLICATE = "duplicate", _("Duplicate")
        REFERRED = "referred", _("Referred elsewhere")
        INVALID = "invalid", _("Not a valid issue")
        WONT_FIX = "wont_fix", _("Won't be fixed")

    class FixedSource(models.TextChoices):
        # Provenance of a fix — citizen-confirmed vs agency-claimed is
        # core data for credible stats ("agency says fixed, community
        # says not" must be representable).
        REPORTER = "reporter", _("Reporter")
        COMMUNITY = "community", _("Community")
        STAFF = "staff", _("Staff")
        AGENCY = "agency", _("Agency")

    class SourceChannel(models.TextChoices):
        WEB = "web", _("Web form")
        URL_IMPORT = "url_import", _("URL import")
        BROWSER_IMPORT = "browser_import", _("Browser import")
        API = "api", _("API")
        STAFF = "staff", _("Staff-filed")

    public_id = models.CharField(
        max_length=12, unique=True, default=generate_public_id, editable=False
    )
    title = models.CharField(_("title"), max_length=200)
    description = models.TextField(_("description"))
    source_url = models.URLField(_("source link"), blank=True)
    location = gis.PointField(_("location"), geography=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.OPEN
    )
    closure_reason = models.CharField(
        _("closure reason"), max_length=20, choices=ClosureReason.choices, blank=True
    )
    fixed_source = models.CharField(
        _("fixed by"), max_length=10, choices=FixedSource.choices, blank=True
    )
    # Duplicate is a real FK, not a text reason: dupes are never
    # dispatched, and closing the canonical issue notifies dupe reporters.
    duplicate_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="duplicates"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, null=True, blank=True, related_name="issues"
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="issues")
    # Snapshots at report time: which areas covered the point, and the
    # geocoded address (Nominatim output drifts; boundaries get redrawn).
    areas = models.ManyToManyField(Area, blank=True, related_name="issues")
    address = models.CharField(_("address"), max_length=255, blank=True)
    # Report-first-verify-later: unconfirmed issues are invisible to
    # public queries. The web channel confirms immediately; channels
    # that need a verification step create with confirmed_at=None.
    confirmed_at = models.DateTimeField(null=True, blank=True, default=timezone.now)
    # Category-driven: dispatched to the agency but never shown publicly.
    non_public = models.BooleanField(default=False)
    # Per-act display anonymity — the name stays visible to staff and is
    # separate from auth (moderators can anonymize a self-doxxing report).
    anonymous = models.BooleanField(default=False)
    source_channel = models.CharField(
        max_length=15, choices=SourceChannel.choices, default=SourceChannel.WEB
    )
    # Notification language for this report (BM/EN), snapshot at intake.
    language = models.CharField(max_length=10, blank=True)
    # Schema room for the "was this fixed?" questionnaire (fast-follow).
    send_questionnaire = models.BooleanField(default=True)
    # Extra answers for Category.extra_fields questions ({name: value}).
    extra_answers = models.JSONField(default=dict, blank=True)
    reporter_name = models.CharField(_("reporter name"), max_length=100, blank=True)
    # Progressive identity: the salted hash of the reporter's secret
    # (raw value shown once at submission), and — once claimed — the
    # account that owns this report. Claimed content earns more trust
    # (higher flag threshold; verified-reporter badge on follow-ups).
    claim_token_hash = models.CharField(max_length=64, blank=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_issues",
    )
    # is_hidden inherited from Flaggable (moderation: hide, never delete).
    # Salted hash of the submitter's IP — abuse tracing without storing PII.
    ip_hash = models.CharField(max_length=64, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = IssueManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["-created_at"],
                condition=models.Q(is_hidden=False),
                name="issue_public_recent",
            )
        ]
        constraints = [
            models.CheckConstraint(
                name="issue_not_duplicate_of_self",
                condition=~models.Q(duplicate_of=models.F("id")),
            )
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("issue_detail", args=[self.public_id])

    @property
    def display_name(self) -> str:
        """What the public sees as the reporter — honours per-act anonymity."""
        return "" if self.anonymous else self.reporter_name

    @property
    def blockers(self) -> "IssueQuerySet":
        """Issues blocking this one ("no crossing at Y" blocks "walk A→B")."""
        return Issue.objects.get_queryset().filter(blocking_links__blocked=self)

    @property
    def blocking(self) -> "IssueQuerySet":
        return Issue.objects.get_queryset().filter(blocked_by_links__blocker=self)

    @property
    def reference_code(self) -> str:
        """Human-quotable reference ("PF-k7xq2mv selesai" is unambiguous)."""
        return f"PF-{self.public_id}"

    @property
    def is_claimed(self) -> bool:
        return self.owner_id is not None

    @property
    def flag_threshold(self) -> int:
        """Claimed reports are harder to flag-bomb off the site."""
        return Flag.CLAIMED_HIDE_THRESHOLD if self.is_claimed else Flag.AUTO_HIDE_THRESHOLD

    def check_claim(self, raw_token: str) -> bool:
        return bool(self.claim_token_hash) and secrets.compare_digest(
            self.claim_token_hash, hash_claim_token(raw_token)
        )

    @property
    def latitude(self) -> float:
        return float(self.location.y)

    @property
    def longitude(self) -> float:
        return float(self.location.x)


class IssueUpdateQuerySet(models.QuerySet["IssueUpdate"]):
    def public(self) -> "IssueUpdateQuerySet":
        return self.filter(is_hidden=False)


class IssueUpdate(Flaggable):
    """
    A public follow-up on an issue — anyone can add one: more evidence,
    "still broken", "contractor came today", a photo. The visible
    conversation is what makes an issue a shared community record.
    """

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="updates")
    text = models.TextField(_("update"))
    author_name = models.CharField(_("name"), max_length=100, blank=True)
    # The status transition this update caused, if any — staff and
    # verified-reporter status changes are updates, giving a free public
    # audit trail of who changed state, when, with what note.
    new_status = models.CharField(
        _("new status"), max_length=10, choices=Issue.Status.choices, blank=True
    )
    # Verified via the reporter secret or the owning account.
    by_reporter = models.BooleanField(default=False)
    photo = models.ImageField(_("photo"), upload_to="updates/%Y/%m/", blank=True)
    # is_hidden inherited from Flaggable.
    ip_hash = models.CharField(max_length=64, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = IssueUpdateQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Update on {self.issue.public_id}"

    @property
    def flag_threshold(self) -> int:
        """Verified-reporter updates are harder to flag-bomb (same rule
        as claimed issues — verified identity buys trust)."""
        return Flag.CLAIMED_HIDE_THRESHOLD if self.by_reporter else Flag.AUTO_HIDE_THRESHOLD


class Flag(models.Model):
    """
    "Report abuse" on an issue or update, by anyone, no login. Deduped
    per submitter (hashed IP); enough distinct flags auto-hides the
    content pending human review (hidden, never deleted).
    """

    AUTO_HIDE_THRESHOLD = 3
    CLAIMED_HIDE_THRESHOLD = 5

    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, related_name="flags", null=True, blank=True
    )
    update = models.ForeignKey(
        IssueUpdate, on_delete=models.CASCADE, related_name="flags", null=True, blank=True
    )
    ip_hash = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "ip_hash"],
                name="unique_issue_flag_per_ip",
                condition=models.Q(issue__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["update", "ip_hash"],
                name="unique_update_flag_per_ip",
                condition=models.Q(update__isnull=False),
            ),
            models.CheckConstraint(
                name="flag_exactly_one_target",
                condition=(
                    models.Q(issue__isnull=False, update__isnull=True)
                    | models.Q(issue__isnull=True, update__isnull=False)
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"Flag on {self.issue_id or self.update_id}"


class IssuePhoto(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(_("photo"), upload_to="issues/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Photo for issue {self.issue_id}"


class IssueLink(models.Model):
    """
    A blocks/blocked-by dependency between issues. Citizens have goals,
    not category codes: "I can't walk from A to B" is blocked by "no
    crossing at Y" and "streetlights broken at Z" — each possibly a
    different agency. The goal issue aggregates its blockers' status.
    """

    blocker = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="blocking_links")
    blocked = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="blocked_by_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="unique_issue_link"),
            models.CheckConstraint(
                name="issue_link_not_self",
                condition=~models.Q(blocker=models.F("blocked")),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.blocker_id} blocks {self.blocked_id}"


class Filing(models.Model):
    """
    One official filing of an issue with one body — many per issue
    (cross-jurisdictional by design). Carries the external reference and
    the *agency's* status: once dispatched, the agency system (SISPAA,
    PBT ticket) is system-of-record for that filing only — a filing
    closing NEVER auto-closes the issue; the community record stays open
    until the problem is actually fixed. Also records community-filed
    parallel complaints ("MPSJ: filed; raised with local councillor"),
    hence body may be blank with a free-text target instead.
    """

    class Channel(models.TextChoices):
        EMAIL = "email", _("Email")
        SISPAA = "sispaa", _("SISPAA")
        MANUAL = "manual", _("Manual / recorded")

    class Status(models.TextChoices):
        # Community-recorded, nothing dispatched by us.
        RECORDED = "recorded", _("Recorded")
        # Dispatch machinery states (send-state machine is separate from
        # the issue's public status).
        QUEUED = "queued", _("Queued")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")
        # Agency-side progress, from status sync or the liaison workflow.
        ACKNOWLEDGED = "acknowledged", _("Acknowledged")
        IN_PROGRESS = "in_progress", _("In progress")
        CLOSED = "closed", _("Closed by agency")

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="filings")
    body = models.ForeignKey(
        Body, on_delete=models.PROTECT, null=True, blank=True, related_name="filings"
    )
    # For targets not modeled as a Body ("local councillor", an MP's office).
    target_name = models.CharField(_("filed with"), max_length=150, blank=True)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.MANUAL)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.RECORDED)
    external_reference = models.CharField(_("their reference number"), max_length=100, blank=True)
    external_status = models.CharField(_("their status"), max_length=100, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    filed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(_("note"), blank=True)
    # Dispatch retry bookkeeping (framework owns retries/dead-lettering).
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="filings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                name="filing_has_target",
                condition=models.Q(body__isnull=False) | ~models.Q(target_name=""),
            )
        ]

    def __str__(self) -> str:
        target = self.body.name if self.body else self.target_name
        return f"{self.issue_id} → {target}"


class Subscription(models.Model):
    """
    "Tell me when this changes" — reporter auto-subscribed to their issue;
    area alerts (radius around a point) reuse the same row via params.
    Delivery machinery (sent-ledger dedup, one-click unsubscribe) comes
    with notifications; the schema exists now because retrofitting the
    entity under a notification system is the expensive direction.
    """

    class Kind(models.TextChoices):
        ISSUE = "issue", _("One issue")
        AREA = "area", _("Reports near a point")

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.ISSUE)
    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, null=True, blank=True, related_name="subscriptions"
    )
    # Kind-specific parameters, e.g. {"lat":…, "lon":…, "radius_m":…}.
    params = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subscriptions",
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    confirmed = models.BooleanField(default=False)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="issue_subscription_has_issue",
                condition=~models.Q(kind="issue") | models.Q(issue__isnull=False),
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} subscription #{self.pk}"
