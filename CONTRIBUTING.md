# Contributing to PleaseFix

PleaseFix is deliberately built so that a large pool of developers of all
levels can contribute safely. The design optimises for **low review
burden and small blast radius** — most of the "is this code okay?"
judgment is automated, so humans review intent, not formatting.

**New here?** Start with the role-based onboarding guide
(`site/contribute.html` — frontend, backend, or AI/integrations, each
with a 10-minute setup and a first-change walkthrough), then pick
something from [docs/GOOD_FIRST_ISSUES.md](docs/GOOD_FIRST_ISSUES.md)
(also rendered at `site/good-first-issues.html`, `/site/` on any
running instance).

## The culture: stone soup

You know the story: travellers arrive in a village with nothing but a
pot and a stone, and announce they're making stone soup. A curious
villager contributes a cabbage to improve it, another some carrots,
another a bit of chicken — and soon there's a rich soup that feeds
everyone, made from a stone. **This project is the stone.** The seed
code is deliberately small and obviously unfinished; it becomes a
platform because people who want a client, an adapter, a translation,
or a map layer drop their piece in the pot.

What that means in practice:

- **Development is informal. Hack, experiment, have fun.** Prototype in
  a branch, open a half-finished PR to talk about it, build something
  weird on the API. Nobody here is your project manager.
- **There is no grand roadmap — scratch your own itch.** The
  [good first issues](docs/GOOD_FIRST_ISSUES.md) and the fast-follows
  in [docs/DESIGN.md](docs/DESIGN.md) are suggestions, not assignments.
  The best contribution is the one you actually want to exist (that's
  how this whole project started).
- **The formality lives in CI, not in people.** The strict tooling
  exists precisely *so that* humans can stay relaxed — reviewers check
  "is this a good idea?", robots check everything else.
- **Minimal code of conduct**: be kind, assume good faith, no
  harassment — of anyone, in any channel. Maintainers will remove
  people who make contributing unfun. That's the whole code.

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

## Your first pull request, step by step

1. **Fork and clone** — fork on GitHub, then
   `git clone git@github.com:YOU/pleasefix.git && cd pleasefix`.
2. **Set up** (once): `cp .env.example .env`, `uv sync`,
   `docker compose up -d db`, then
   `uv run python manage.py migrate && uv run python manage.py seed_sample_data`.
   (Windows: see `docs/ONBOARDING-WINDOWS.md`. Full stack instead:
   `docker compose up`.)
3. **Look around** — the interactive walkthrough (`site/dev.html`, or
   `/site/dev.html` on your running instance) shows the architecture,
   a report's journey, and every data model in ~10 minutes.
4. **Pick something** — a [good first issue](docs/GOOD_FIRST_ISSUES.md),
   a role track (`site/contribute.html`), or your own itch. Say so on
   the issue tracker so nobody doubles up.
5. **Branch and hack** — `git switch -c fix/streetlight-form`. Run
   `uv run python manage.py runserver` and poke at
   http://localhost:8000. Have fun; half-formed ideas are fine.
6. **Run the gauntlet** (this is exactly what CI runs):
   `compilemessages`, `ruff check`, `ruff format --check`, `mypy`,
   `lint-imports`, `pytest`, and the generated-artifact checks
   (`export_openapi_schema`, `export_good_first_issues` + clean
   `git diff`). Green locally means green in CI.
7. **Commit** (style below), **push**, and **open the PR** against
   `main`. Describe the *why* in a sentence or two — a screenshot if
   it's visual.
8. **What happens next**: CI does the style/type/test judgment; a human
   reviews the idea. Expect friendly, small-diff-loving review.
   Migrations, if any, get split into their own PR (maintainer-gated).

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

`docker compose up --build` is the entire stack, with live reload in
development (source is bind-mounted; edits apply instantly). A VS Code
Dev Container is included (`.devcontainer/`) — "Reopen in Container"
gives you the stack plus ruff/mypy/pytest pre-wired. Windows developers:
start from [docs/ONBOARDING-WINDOWS.md](docs/ONBOARDING-WINDOWS.md).
Fake adapters keep development self-contained: OTP prints to the
console, no Meta/WhatsApp business verification ever needed for local
work. See README for the non-Docker path.
