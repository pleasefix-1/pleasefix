"""
/api/v1 — the public API.

The OpenAPI schema generated from this module is a reviewed repo artifact
(api/openapi.json): regenerate with `manage.py export_openapi_schema`;
CI fails on unintended API surface changes. Additive changes anytime;
breaking changes only in a future /api/v2. See docs/DESIGN.md §7.
"""

from django.http import HttpRequest
from ninja import NinjaAPI, Schema

api_v1 = NinjaAPI(
    title="PleaseFix API",
    version="1.0.0",
    description="Public API for the PleaseFix civic issue tracker.",
)


class VersionOut(Schema):
    name: str
    api_version: str


@api_v1.get("/version", response=VersionOut, summary="API name and version")
def version(request: HttpRequest) -> VersionOut:
    return VersionOut(name="pleasefix", api_version="1.0.0")
