"""Domain-model invariants: routing, lifecycle, filings, dependencies.

These are the tripwires from docs/DESIGN.md §3 — they encode decisions
(multi-body overlap is normal, a filing closing never closes the issue,
duplicates are a real FK) so a later change that breaks one fails loudly.
"""

import pytest
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.db import IntegrityError, transaction

from core.models import Area, Body, Category, Filing, Issue, IssueLink, Tag

pytestmark = pytest.mark.django_db

# A point inside Subang Jaya and two overlapping boxes around it.
SUBANG = Point(101.5183, 3.0738, srid=4326)


def box(minx: float, miny: float, maxx: float, maxy: float) -> MultiPolygon:
    return MultiPolygon(Polygon.from_bbox((minx, miny, maxx, maxy)), srid=4326)


def make_area(name: str = "MPSJ area", **kwargs: object) -> Area:
    defaults: dict[str, object] = {"boundary": box(101.4, 3.0, 101.7, 3.2)}
    defaults.update(kwargs)
    return Area.objects.create(name=name, **defaults)


def make_body(name: str, area: Area | None = None) -> Body:
    body = Body.objects.create(name=name, slug=name.lower().replace(" ", "-"))
    if area is not None:
        body.areas.add(area)
    return body


def make_issue(**overrides: object) -> Issue:
    kwargs: dict[str, object] = {
        "title": "Broken streetlight",
        "description": "Out for two weeks.",
        "longitude": SUBANG.x,
        "latitude": SUBANG.y,
    }
    kwargs.update(overrides)
    issue, _token = Issue.objects.create_report(**kwargs)  # type: ignore[arg-type]
    return issue


class TestRouting:
    def test_categories_for_point_is_union_across_overlapping_bodies(self) -> None:
        area = make_area()
        pbt = make_body("MPSJ", area)
        utility = make_body("TNB", area)
        elsewhere = make_body("MBPP", make_area("Penang", boundary=box(100.2, 5.3, 100.4, 5.5)))
        c1 = Category.objects.create(body=pbt, name="Streetlight", state=Category.State.CONFIRMED)
        c2 = Category.objects.create(
            body=utility, name="Streetlight", state=Category.State.CONFIRMED
        )
        Category.objects.create(body=elsewhere, name="Streetlight", state=Category.State.CONFIRMED)

        found = set(Category.objects.for_point(SUBANG))
        assert found == {c1, c2}

    def test_unconfirmed_and_inactive_categories_are_not_offered(self) -> None:
        area = make_area()
        pbt = make_body("MPSJ", area)
        Category.objects.create(body=pbt, name="New category")  # unconfirmed by default
        Category.objects.create(body=pbt, name="Old category", state=Category.State.INACTIVE)

        assert Category.objects.for_point(SUBANG).count() == 0

    def test_inactive_area_generation_is_ignored(self) -> None:
        old = make_area("MPSJ 2019 boundary", is_active=False)
        body = make_body("MPSJ", old)
        Category.objects.create(body=body, name="Pothole", state=Category.State.CONFIRMED)

        assert Category.objects.for_point(SUBANG).count() == 0

    def test_category_name_unique_per_body_not_globally(self) -> None:
        a, b = make_body("MPSJ"), make_body("MBSJ")
        Category.objects.create(body=a, name="Pothole")
        Category.objects.create(body=b, name="Pothole")  # fine: per-body join
        with pytest.raises(IntegrityError):
            Category.objects.create(body=a, name="Pothole")


class TestIssueLifecycle:
    def test_report_snapshots_covering_areas(self) -> None:
        inside = make_area()
        make_area("Penang", boundary=box(100.2, 5.3, 100.4, 5.5))
        issue = make_issue()
        assert list(issue.areas.all()) == [inside]

    def test_zero_matched_areas_is_accepted_not_rejected(self) -> None:
        issue = make_issue()
        assert issue.areas.count() == 0
        assert issue in Issue.objects.public()

    def test_unconfirmed_issue_is_not_public(self) -> None:
        issue = make_issue()
        assert issue in Issue.objects.public()
        Issue.objects.filter(pk=issue.pk).update(confirmed_at=None)
        assert issue not in Issue.objects.public()

    def test_non_public_category_makes_issue_non_public(self) -> None:
        body = make_body("MPSJ")
        welfare = Category.objects.create(
            body=body, name="Salah laku", state=Category.State.CONFIRMED, non_public=True
        )
        issue = make_issue(category=welfare)
        assert issue.non_public
        assert issue not in Issue.objects.public()

    def test_anonymous_report_hides_name_from_display_only(self) -> None:
        issue = make_issue(reporter_name="Aina", anonymous=True)
        assert issue.display_name == ""
        assert issue.reporter_name == "Aina"  # staff still see it

    def test_issue_cannot_be_duplicate_of_itself(self) -> None:
        issue = make_issue()
        issue.duplicate_of = issue
        with pytest.raises(IntegrityError):
            issue.save()

    def test_duplicate_is_a_real_link(self) -> None:
        canonical = make_issue()
        dupe = make_issue()
        dupe.duplicate_of = canonical
        dupe.status = Issue.Status.CLOSED
        dupe.closure_reason = Issue.ClosureReason.DUPLICATE
        dupe.save()
        assert dupe in canonical.duplicates.all()


class TestFilings:
    def test_many_filings_per_issue_and_agency_close_never_closes_issue(self) -> None:
        area = make_area()
        issue = make_issue()
        mpsj = make_body("MPSJ", area)
        prasarana = make_body("Prasarana", area)
        f1 = Filing.objects.create(issue=issue, body=mpsj, channel=Filing.Channel.EMAIL)
        Filing.objects.create(issue=issue, body=prasarana)
        Filing.objects.create(issue=issue, target_name="Local councillor")

        # The agency closes its ticket ("selesai"); the community record
        # stays open — closing the issue is a separate, human decision.
        f1.status = Filing.Status.CLOSED
        f1.external_status = "Selesai"
        f1.save()
        issue.refresh_from_db()
        assert issue.status == Issue.Status.OPEN
        assert issue.filings.count() == 3

    def test_filing_requires_a_body_or_a_named_target(self) -> None:
        issue = make_issue()
        with pytest.raises(IntegrityError):
            Filing.objects.create(issue=issue)


class TestDependenciesAndTags:
    def test_blocks_blocked_by_links(self) -> None:
        goal = make_issue(title="Can't walk from LRT to the shops")
        crossing = make_issue(title="No crossing at Persiaran Kewajipan")
        lights = make_issue(title="Streetlights out along the walkway")
        IssueLink.objects.create(blocker=crossing, blocked=goal)
        IssueLink.objects.create(blocker=lights, blocked=goal)

        assert set(goal.blockers) == {crossing, lights}
        assert list(crossing.blocking) == [goal]

    def test_issue_cannot_block_itself(self) -> None:
        issue = make_issue()
        with pytest.raises(IntegrityError):
            IssueLink.objects.create(blocker=issue, blocked=issue)

    def test_dependency_links_are_deduped(self) -> None:
        a, b = make_issue(), make_issue()
        IssueLink.objects.create(blocker=a, blocked=b)
        with pytest.raises(IntegrityError), transaction.atomic():
            IssueLink.objects.create(blocker=a, blocked=b)

    def test_community_tags(self) -> None:
        issue = make_issue()
        a11y = Tag.objects.create(name="a11y")
        issue.tags.add(a11y)
        assert issue in a11y.issues.all()
