from typing import Any

from django.conf import settings
from django.http import HttpRequest


def site_settings(request: HttpRequest) -> dict[str, Any]:
    return {
        "SITE_NAME": settings.SITE_NAME,
        "MAP_CENTER": settings.MAP_CENTER,
        "MAP_DEFAULT_ZOOM": settings.MAP_DEFAULT_ZOOM,
    }
