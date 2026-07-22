from django.contrib.gis.db import models as gis
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


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

    title = models.CharField(_("title"), max_length=200)
    description = models.TextField(_("description"))
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
        return reverse("issue_detail", args=[self.pk])

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
