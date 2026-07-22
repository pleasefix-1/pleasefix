# AGENTS.md — working on PleaseFix

Guidance for AI coding agents (and humans in a hurry). PleaseFix is a
public, community-owned civic issue tracker for Malaysia — Django +
GeoDjango, HTMX server-rendered UI, django-ninja API. Read
[docs/DESIGN.md](docs/DESIGN.md) for architecture and decisions and
[CONTRIBUTING.md](CONTRIBUTING.md) for the trust-gradient rules before
changing anything non-trivial.

## Setup

```sh
cp .env.example .env        # required: settings refuse to boot without env
uv sync                     # deps into .venv (Python >= 3.12)
docker compose up --build   # full stack: app, worker, PostGIS, Redis, S3, Caddy
```

- Tests and `manage.py` need PostGIS. Easiest: keep the compose `db`
  running and set `DATABASE_URL=postgis://pleasefix:pleasefix@localhost:5432/pleasefix`.
- macOS: uncomment `GDAL_LIBRARY_PATH`/`GEOS_LIBRARY_PATH` in `.env`
  (Homebrew paths are pre-filled). Linux/containers find GDAL unaided.
- `DEBUG=false` triggers production boot guards (real `SECRET_KEY`,
  `REDIS_URL` required). Develop and run CI with `DEBUG=true`.

## Verify before committing (this is CI, in order)

```sh
uv run python manage.py compilemessages
uv run ruff check .
uv run ruff format --check .
uv run mypy .                  # strict + django-stubs; not optional
uv run lint-imports
uv run pytest
uv run python manage.py export_openapi_schema && git diff --exit-code api/openapi.json
```

A change is not done until all seven pass. `api/openapi.json` is a
committed, reviewed artifact: if you change API surface, regenerate it
and commit the diff.

## Map

| Path | What | Notes |
|---|---|---|
| `config/` | settings, urls, celery, wsgi | 12-factor: deploy values come from env, never code literals |
| `core/` | domain: models, views, forms, importers, abuse controls | **protected core** — maintainer review; import-linter forbids `core` → `api` |
| `api/` | django-ninja v1 API + OpenAPI export | depends inward on `core`, never the reverse |
| `templates/`, `static/` | server-rendered HTMX UI | `static/js/htmx.min.js` is vendored — no CDNs, no npm |
| `locale/ms/` | Bahasa Melayu translations | `makemessages -l ms`, then `compilemessages`; keep BM/EN in sync |
| `locale_vendor/` | BM translations for third-party apps (allauth) | |
| `core/tests/`, `conftest.py` | pytest + pytest-django + factory-boy | tests hit real PostGIS, no mocked ORM |
| `docs/`, `site/` | public docs & onboarding | reference concrete file paths — update them when layout changes |
| `site/dev.html` | interactive developer walkthrough (architecture, report journey, data model) | maintained artifact: `core/tests/test_dev_site.py` fails CI if a core model is missing from it or a referenced file moved — update it in the same PR |
| `.github/workflows/ci.yml` | the gauntlet above | runs with `DEBUG=true` |

## Rules that bite

- **Never weaken a boot guard, rate limit, or abuse control to make a
  test pass.** They are the product (see `core/abuse.py`, docs/ABUSE.md).
- **No new runtime dependencies** without discussion — the stack is
  deliberately boring and small.
- **No secrets, no personal identity** in code, fixtures, or commits.
  Commit as the repo-configured git user.
- Migrations live in the protected core: additive and reversible;
  `django-migration-linter` is in the dev group — use it.
- i18n: user-facing strings go through `gettext`/`{% trans %}` from the
  start; English-only strings are a bug, not a TODO.
- Deploy-specific values (brand, map center, hosts) come from env via
  `config/settings.py` — adding a code literal for one is a regression.
- This project takes no code from FixMyStreet or other GPL codebases —
  ideas yes, code never.

## For agents specifically

- **Use an LSP, not grep-and-hope.** `basedpyright`/`pyright` and
  `ruff server` work out of the box against `.venv` (created by
  `uv sync`). Prefer go-to-definition/references over text search for
  Django models and views; `mypy` strict is the type oracle.
- **Small diffs win.** The review model here is "humans review intent,
  tooling reviews everything else" — keep changes scoped so the gauntlet
  does the heavy lifting.
- **Match existing idiom** — look at a neighboring view/form/test before
  writing a new one. `core/views.py` and `core/tests/` are the reference
  style.
- If your harness supports skills/commands, a code-review or
  security-review pass over your diff before pushing is worth it —
  abuse-control and identity-handling code is security-sensitive.
- When you change file layout or commands, update this file,
  `site/contribute.html`, `site/dev.html`, and
  `docs/GOOD_FIRST_ISSUES.md` in the same change — onboarding docs that
  lie are worse than none. For `dev.html` the sync is enforced:
  `core/tests/test_dev_site.py` fails when a model is missing from the
  walkthrough or a referenced file moved.
