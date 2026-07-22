import secrets

from django.contrib.gis.db import models as gis
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

# Unambiguous lowercase alphabet (no 0/1/i/l/o) for short public IDs.
PUBLIC_ID_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"


def generate_public_id() -> str:
    """Short, random, stable issue ID, e.g. 'k7xq2mv' — used in URLs and
    as the human reference code ("PF-k7xq2mv"). 31^7 ≈ 2.7e10 values, so
    random collisions are vanishingly rare; uniqueness is DB-enforced."""
    return "".join(secrets.choice(PUBLIC_ID_ALPHABET) for _ in range(7))


class Issue(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("issue_detail", args=[self.public_id])

    @property
    def reference_code(self) -> str:
        """Human-quotable reference ("PF-k7xq2mv selesai" is unambiguous)."""
        return f"PF-{self.public_id}"

    @property
    def latitude(self) -> float:
        return float(self.location.y)

    @property
    def longitude(self) -> float:
        return float(self.location.x)


class IssuePhoto(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(_("photo"), upload_to="issues/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Photo for issue {self.issue_id}"
