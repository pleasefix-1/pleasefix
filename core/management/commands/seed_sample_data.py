"""
Seed the database with sample data for development.

Idempotent: running it twice adds nothing. Intended for dev/demo
environments only — refuses to run with DEBUG off unless --force.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from core.models import Issue

SAMPLE_PHOTO = Path(__file__).resolve().parents[2] / "fixtures" / "sample" / "longkang-ss2-24.jpg"


@dataclass(frozen=True)
class Sample:
    title: str
    description: str
    longitude: float
    latitude: float
    reporter_name: str
    photo: Path | None = None


SAMPLE_ISSUES = [
    Sample(
        title="Longkang tersumbat di Jalan SS2/24",
        description="Blocked drain flooding the walkway after rain. "
        "Rubbish and leaves have piled up at the grate for weeks.",
        longitude=101.6212,
        latitude=3.1173,
        reporter_name="Chin",
        photo=SAMPLE_PHOTO,
    ),
    Sample(
        title="Streetlight out near the playground, Jalan 14/29",
        description="The whole stretch between the playground and the "
        "surau is dark at night; out for at least two weeks.",
        longitude=101.6280,
        latitude=3.1121,
        reporter_name="Aina",
    ),
]


class Command(BaseCommand):
    help = "Insert sample issues (with photo) for development. Idempotent."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--force", action="store_true", help="Allow seeding even with DEBUG off."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to seed sample data with DEBUG off (use --force).")

        created = 0
        for sample in SAMPLE_ISSUES:
            if Issue.objects.filter(title=sample.title).exists():
                continue
            issue = Issue.objects.create(
                title=sample.title,
                description=sample.description,
                location=Point(sample.longitude, sample.latitude, srid=4326),
                reporter_name=sample.reporter_name,
            )
            if sample.photo is not None:
                with sample.photo.open("rb") as f:
                    issue.photos.create(image=File(f, name=sample.photo.name))
            created += 1
        self.stdout.write(f"seeded {created} issue(s), {Issue.objects.count()} total")
