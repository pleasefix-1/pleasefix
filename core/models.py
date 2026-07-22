import hashlib
import secrets
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.gis.db import models as gis
from django.contrib.gis.geos import Point
from django.db import IntegrityError, models
from django.urls import reverse
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


class IssueQuerySet(models.QuerySet["Issue"]):
    def public(self) -> "IssueQuerySet":
        return self.filter(is_hidden=False)


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
    ) -> tuple["Issue", str]:
        """Create an issue and return (issue, raw_claim_token). The raw
        token is shown once and never stored; retries on the astronomically
        rare public_id collision instead of 500-ing."""
        claim_token = generate_claim_token()
        for _attempt in range(5):
            try:
                issue = self.create(
                    title=title,
                    description=description,
                    location=Point(longitude, latitude, srid=4326),
                    reporter_name=reporter_name,
                    source_url=source_url,
                    ip_hash=ip_hash,
                    owner_id=owner.pk if owner is not None else None,
                    claim_token_hash=hash_claim_token(claim_token),
                )
                return issue, claim_token
            except IntegrityError:
                continue  # public_id collision — regenerate via default
        raise IntegrityError("could not allocate a unique public_id")


class Issue(Flaggable):
    """
    A community issue. Deliberately minimal first slice — categories,
    agencies, filings, dependencies, and moderation land with the full
    domain model (docs/DESIGN.md §10).
    """

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        FIXED = "fixed", _("Fixed")
        CLOSED = "closed", _("Closed")

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

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("issue_detail", args=[self.public_id])

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
