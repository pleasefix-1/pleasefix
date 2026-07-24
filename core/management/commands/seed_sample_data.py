"""
Seed the database with sample data for development.

Idempotent: running it twice adds nothing. Intended for dev/demo
environments only — refuses to run with DEBUG off unless --force.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from core.models import Area, Body, Category, CategoryGroup, Issue, Media

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

        self._seed_routing()
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
                    media = Media.objects.create(file=File(f, name=sample.photo.name), kind="image")
                issue.media.create(media=media)
            created += 1
        self.stdout.write(f"seeded {created} issue(s), {Issue.objects.count()} total")

    def _seed_routing(self) -> None:
        """One sample area/body/category chain so the routing admin and
        the report form have something to show. Real boundaries are
        imported/drawn by admins — this is a dev-only rough bbox."""
        if Body.objects.exists():
            return
        area = Area.objects.create(
            name="Petaling Jaya (sample bbox)",
            kind=Area.Kind.COUNCIL,
            boundary=MultiPolygon(Polygon.from_bbox((101.56, 3.05, 101.68, 3.17)), srid=4326),
        )
        body = Body.objects.create(
            name="MBPJ (sample)", slug="mbpj-sample", dispatch_email="aduan@example.invalid"
        )
        body.areas.add(area)
        infra = CategoryGroup.objects.create(name="Roads & drains", order=1)
        for name, group in [
            ("Longkang tersumbat / blocked drain", infra),
            ("Pothole", infra),
            ("Streetlight not working", None),
        ]:
            Category.objects.create(
                body=body, name=name, group=group, state=Category.State.CONFIRMED
            )
        self.stdout.write("seeded sample routing (1 area, 1 body, 3 categories)")
