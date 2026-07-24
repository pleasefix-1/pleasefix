from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command

from core.models import Issue

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media_tmp(settings: Any, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path


def test_seed_is_idempotent_and_attaches_photo(settings: Any) -> None:
    settings.DEBUG = True
    call_command("seed_sample_data")
    call_command("seed_sample_data")
    issues = Issue.objects.all()
    assert issues.count() == 2
    longkang = Issue.objects.get(title__startswith="Longkang")
    assert longkang.media.count() == 1


def test_seed_refuses_without_debug(settings: Any) -> None:
    settings.DEBUG = False
    with pytest.raises(Exception, match="DEBUG off"):
        call_command("seed_sample_data")
    call_command("seed_sample_data", "--force")
    assert Issue.objects.count() == 2
