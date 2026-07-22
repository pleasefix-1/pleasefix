# PleaseFix

**A public, community-owned civic issue tracker for Malaysia.** Report
local problems (potholes, broken streetlights, blocked drains, barriers),
get them routed to the responsible agencies, and — unlike official
channels — keep the issue **open and public until it is actually fixed**,
with every filing, photo, and status change on the record.

Inspired by FixMyStreet; built as an independent open platform.
**Why this exists alongside SISPAA and agency hotlines:** see
[docs/WHY.md](docs/WHY.md). Architecture and decisions:
[docs/DESIGN.md](docs/DESIGN.md). Want to help?
[CONTRIBUTING.md](CONTRIBUTING.md).

## Status

**Seed.** Runnable skeleton with the full production topology; the domain
model and report flow land next. Everything below already works.

## Quickstart

```sh
cp .env.example .env
docker compose up --build
```

On **Windows**? Follow the from-scratch guide:
[docs/ONBOARDING-WINDOWS.md](docs/ONBOARDING-WINDOWS.md) (WSL2 + Docker
Desktop, or a one-click VS Code Dev Container). In development the
stack auto-reloads on code edits (`compose.override.yaml`); production
runs `docker compose -f compose.yaml up -d` to skip the dev overrides.

- App: http://localhost:8000 (also via Caddy on :80)
- API + interactive docs: http://localhost:8000/api/v1/docs
- Health: http://localhost:8000/healthz
- Admin: http://localhost:8000/admin/ (`docker compose exec app python manage.py createsuperuser`)

That single command is the whole stack — the same shape we deploy to
production (Django app, Celery worker, PostgreSQL+PostGIS, Redis,
VersityGW S3 storage, Caddy). No cloud accounts, no API keys.

### Local (non-Docker) development

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), GDAL/GEOS
(macOS: `brew install gdal`, then set `GDAL_LIBRARY_PATH`/
`GEOS_LIBRARY_PATH` in `.env` — see `.env.example`), and a
Postgres+PostGIS reachable via `DATABASE_URL` (easiest:
`docker compose up db`).

```sh
uv sync
uv run manage.py migrate
uv run manage.py runserver
```

Checks (all enforced in CI):

```sh
uv run ruff check . && uv run ruff format --check .
uv run mypy .
uv run pytest
uv run lint-imports
```

## Stack

- **Django + GeoDjango** (Python, strictly typed), PostgreSQL + PostGIS
- Server-rendered templates + **HTMX** (vendored, no CDN)
- **django-ninja** API at `/api/v1/` — the OpenAPI schema
  (`api/openapi.json`) is a reviewed artifact; regenerate with
  `manage.py export_openapi_schema`
- **Celery** background jobs; **Caddy** front proxy (auto-TLS in prod);
  **VersityGW** bundled S3-compatible photo storage (posix backend:
  photos are plain files on disk)
- Bahasa Melayu + English from day one

## License

[Apache-2.0](LICENSE). Permissive by intent: use it, fork it, deploy it
for your city, build commercial services on it. The explicit patent
grant and standard contribution terms (inbound = outbound, no CLA
needed) are why Apache-2.0 over MIT. See [NOTICE](NOTICE).
