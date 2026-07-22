from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _non_manifest_staticfiles(settings: Any) -> None:
    """Tests don't run collectstatic, so skip the hashed-manifest storage."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
