# Contributing to PleaseFix

PleaseFix is deliberately built so that a large pool of developers of all
levels can contribute safely. The design optimises for **low review
burden and small blast radius** — most of the "is this code okay?"
judgment is automated, so humans review intent, not formatting.

## Where to contribute (trust gradient)

- **Contribution zones — start here:**
  - *Inbound channel adapters* (web form is the reference; WhatsApp, SMS,
    agency-email parsers later) — each adapter produces a normalized
    `IncomingReport` into the core intake service.
  - *Dispatch adapters* (outbound to agencies) — email is the floor and
    the worked example; you write only "send it", the framework owns
    retries, dead-lettering, idempotency. One agency's breakage stays
    that agency's breakage.
  - *Client templates* (separate repos) and anything built on the public
    API — see "Build a client" below.
  - Config, translations (BM/EN), documentation.
- **Protected core** (maintainers only, enforced by CODEOWNERS +
  import-linter): report lifecycle, geo queries, auth, the dispatch
  framework, migrations, and the OpenAPI schema file.

New contributors start in adapters/templates and earn inward.

## Ground rules (enforced by CI, not by reviewers)

- Formatting/linting is applied, not requested: **Ruff** (format + lint).
- **Strict typing** (mypy, django-stubs). Types are the first-pass review.
- **Coverage floor on changed lines**; golden-path tests + factories
  (factory_boy) make writing tests low-friction.
- **PR size limit** (override label exists for genuine exceptions).
- **No raw SQL in contributions** — ORM only. The few necessary raw geo
  queries live in the core.
- **Migrations are maintainer-gated**: always in their own PR, checked by
  django-migration-linter. Don't include migrations in feature PRs.
- Module boundaries are mechanical: `lint-imports` must pass.
- User-facing strings are translatable (`{% translate %}` / `gettext`)
  from the first line — BM + EN are both launch languages.

## Build a client instead

The product for developers is **the API plus a 15-minute path to a
running client**. If you'd rather build than patch: the OpenAPI schema
lives at `api/openapi.json` (interactive docs at `/api/v1/docs`), SDKs
and thin client templates (SPA and HTMX/BFF) are published separately,
and a hosted sandbox with seeded Malaysian data is planned so you never
need Docker or PostGIS to build against the API. Community clients get
listed in the registry — recognition is the currency.

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): summary` — types in use: `feat`, `fix`, `docs`, `chore`,
`refactor`, `test`, `ci`. Keep one logical change per commit; the body
explains why, not what.

## License of contributions

The project is Apache-2.0. By submitting a contribution you agree it is
licensed under Apache-2.0 too (this is Section 5 of the license — no
separate CLA to sign). Never copy code from AGPL/GPL projects
(including FixMyStreet) into this codebase.

## Dev environment

`docker compose up --build` is the entire stack. Fake adapters keep
development self-contained: OTP prints to the console, no Meta/WhatsApp
business verification ever needed for local work. See README for the
non-Docker path.
