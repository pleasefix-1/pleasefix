"""site/dev.html (the developer walkthrough) is a maintained artifact.

These tests make "keep the walkthrough updated" a CI failure instead of
a hope: every concrete core model must appear in the page's data-model
explorer, and every file the page points at must actually exist.
"""

import re
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.test import Client

DEV_HTML = Path(settings.BASE_DIR) / "site" / "dev.html"


def test_every_core_model_is_in_the_walkthrough() -> None:
    # Cards are built from the MODELS object in the page's script; its
    # keys are the contract ("Name: {group:"). If a reformat ever breaks
    # this regex the set comes back empty and the test fails loudly —
    # it cannot silently pass.
    html = DEV_HTML.read_text()
    documented = set(re.findall(r"^  (\w+): \{group:", html, re.MULTILINE))
    actual = {m.__name__ for m in apps.get_app_config("core").get_models()}
    missing = actual - documented
    assert not missing, (
        f"site/dev.html is missing model card(s) for: {sorted(missing)}. "
        "Add them to the MODELS object in the same PR that adds the model."
    )
    stale = documented - actual
    assert not stale, (
        f"site/dev.html documents model(s) that no longer exist: {sorted(stale)}. "
        "Remove or rename their cards."
    )


@pytest.mark.django_db
def test_walkthrough_is_served_and_linked_from_the_app() -> None:
    client = Client()
    page = client.get("/site/dev.html")
    assert page.status_code == 200
    assert b"How <span>PleaseFix</span> works" in page.content
    # The crumbs' relative links must resolve within the app too.
    assert client.get("/site/index.html").status_code == 200
    assert client.get("/site/contribute.html").status_code == 200
    # Discoverable from every app page via the footer.
    home = client.get("/")
    assert b'href="/site/dev.html"' in home.content


@pytest.mark.django_db
def test_site_page_view_serves_only_site_html() -> None:
    assert Client().get("/site/nope.html").status_code == 404


@pytest.mark.django_db
def test_good_first_issues_page_is_served_and_fresh() -> None:
    from core.management.commands.export_good_first_issues import PAGE_TEMPLATE, REPO_BLOB
    from core.management.commands.export_good_first_issues import render_markdown as render

    response = Client().get("/site/good-first-issues.html")
    assert response.status_code == 200
    assert b"Good first issues" in response.content

    source = (Path(settings.BASE_DIR) / "docs" / "GOOD_FIRST_ISSUES.md").read_text()
    expected = PAGE_TEMPLATE.format(body=render(source), blob=REPO_BLOB)
    committed = (Path(settings.BASE_DIR) / "site" / "good-first-issues.html").read_text()
    assert committed == expected, (
        "site/good-first-issues.html is stale — docs/GOOD_FIRST_ISSUES.md changed. "
        "Run: python manage.py export_good_first_issues and commit the result."
    )


def test_every_referenced_file_exists() -> None:
    html = DEV_HTML.read_text()
    referenced = set(re.findall(r'data-file="([^"]+)"', html))
    assert referenced, "expected data-file references in site/dev.html"
    missing = [p for p in sorted(referenced) if not (Path(settings.BASE_DIR) / p).exists()]
    assert not missing, (
        f"site/dev.html points at file(s) that moved or vanished: {missing}. "
        "Update the walkthrough to match the new layout."
    )
