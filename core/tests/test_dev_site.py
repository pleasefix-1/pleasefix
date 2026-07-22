"""site/dev.html (the developer walkthrough) is a maintained artifact.

These tests make "keep the walkthrough updated" a CI failure instead of
a hope: every concrete core model must appear in the page's data-model
explorer, and every file the page points at must actually exist.
"""

import re
from pathlib import Path

from django.apps import apps
from django.conf import settings

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


def test_every_referenced_file_exists() -> None:
    html = DEV_HTML.read_text()
    referenced = set(re.findall(r'data-file="([^"]+)"', html))
    assert referenced, "expected data-file references in site/dev.html"
    missing = [p for p in sorted(referenced) if not (Path(settings.BASE_DIR) / p).exists()]
    assert not missing, (
        f"site/dev.html points at file(s) that moved or vanished: {missing}. "
        "Update the walkthrough to match the new layout."
    )
