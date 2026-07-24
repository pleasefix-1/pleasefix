"""Delete abandoned async uploads — Media never attached to any issue.

The async-upload flow (docs/media-library-phase2.md) creates a Media row
as soon as a file is uploaded, before the report is submitted; a reporter
who closes the tab leaves it orphaned. Run this periodically (Celery beat
is not wired yet — invoke from cron/manually for now)."""

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Media


class Command(BaseCommand):
    help = "Delete uploaded media never attached to an issue (abandoned async uploads)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Only delete orphans older than this many hours (default 24).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        cutoff = timezone.now() - timedelta(hours=options["hours"])
        orphans = list(Media.objects.orphans(cutoff))
        for media in orphans:
            media.file.delete(save=False)  # remove the stored file, then the row
            media.delete()
        self.stdout.write(f"deleted {len(orphans)} orphan media")
