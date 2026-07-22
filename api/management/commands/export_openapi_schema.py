import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from api.v1 import api_v1


class Command(BaseCommand):
    help = "Write the OpenAPI schema to api/openapi.json (a reviewed repo artifact)."

    def handle(self, *args: Any, **options: Any) -> None:
        out = Path(__file__).resolve().parents[2] / "openapi.json"
        schema = api_v1.get_openapi_schema()
        out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        self.stdout.write(f"wrote {out}")
