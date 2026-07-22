# Role-based onboarding tracks

Pick the track that fits you, make one small change, and grow from
there.

> **Prefer the interactive version.** This page mirrors
> [`site/contribute.html`](../site/contribute.html) — on any running
> instance it's at `/site/contribute.html`. This markdown version exists
> so the same content reads well here on GitHub.

Related: [WALKTHROUGH.md](WALKTHROUGH.md) (how everything works) ·
[CONTRIBUTING](../CONTRIBUTING.md) (culture, first-PR guide) ·
[good first issues](GOOD_FIRST_ISSUES.md)

## First, get it running (10 minutes)

The whole stack is one command — you never install Python, GDAL, or a
database on your machine:

```sh
git clone https://github.com/pleasefix-1/pleasefix.git
cd pleasefix
cp .env.example .env
docker compose up --build          # → http://localhost:8000
docker compose exec app python manage.py seed_sample_data
```

On Windows, follow [ONBOARDING-WINDOWS.md](ONBOARDING-WINDOWS.md).
Run the checks anytime:
`docker compose exec app sh -c "ruff check . && mypy . && pytest"`.

**How the code is shaped:** a modular monolith. The *protected core*
(report lifecycle, geo queries, auth, dispatch framework) is
maintainer-owned; *contribution zones* — channel adapters, client
templates, config, translations — are where you start and earn inward.
CI applies formatting and types for you, so review is about ideas.

## 🎨 Frontend track

**You'll work in:** `templates/`, `static/`, `core/forms.py`. The app
is server-rendered Django templates with HTMX for enhancement — the
lowest-skill-floor path on purpose. Two rules: every user-facing string
is wrapped in `{% translate %}`/`{% blocktranslate %}` (Bahasa Melayu +
English are both first-class), and everything must still work with
JavaScript off.

**Your first change: a status badge colour**

1. Open `http://localhost:8000/issues/` — the seeded issues with status
   pills.
2. Find the `.status` rules in `templates/issues/list.html` and tweak
   the "fixed" colour.
3. Reload — the dev server auto-reloads. Toggle your OS dark mode to
   check both themes.
4. Added English text? `docker compose exec app python manage.py
   makemessages -l ms`, then translate in
   `locale/ms/LC_MESSAGES/django.po`.

Ready for a real one? Consolidating the inline CSS into
`static/css/site.css`, or wiring the flag button through HTMX — see
[good first issues](GOOD_FIRST_ISSUES.md).

## ⚙️ Backend track

**You'll work in:** `core/models.py`, `core/views.py`, `api/v1.py`,
`core/importers.py`. Strict typing (mypy) and ORM-only (no raw SQL) are
enforced in CI. Migrations ship in their own PR. Geo data is GeoDjango
on PostGIS — points are `PointField(geography=True)`.

**Your first change: add a field to the API**

1. Open `http://localhost:8000/api/v1/docs` — the live API explorer.
   Hit `GET /issues`.
2. In `api/v1.py`, add a field to `IssueOut` (e.g. `status_display`)
   and populate it in `_issue_out`.
3. Regenerate the reviewed schema:
   `docker compose exec app python manage.py export_openapi_schema` —
   CI fails if `api/openapi.json` is stale.
4. Add a line to a test in `core/tests/` and run `pytest`.

Then try: the Reddit comment-permalink fix, the first Celery task
(EXIF-strip photos), or a PostGIS nearby-issues query — all in
[good first issues](GOOD_FIRST_ISSUES.md).

## 🤖 AI / integrations track

**The product for you is the API.** PleaseFix is designed so
third-party clients, bots, and AI features are first-class — you don't
need to touch the core to build on it. The OpenAPI schema is
`api/openapi.json`; live docs at `/api/v1/docs`.

**Your first change: talk to the API**

1. With the stack running:
   `curl http://localhost:8000/api/v1/issues`.
2. Write a short script that reads the JSON and prints each issue's
   reference code and location — drop it in a new `examples/` directory.
3. Submit a report through the form flow, then fetch it back:
   `GET /api/v1/issues/<id>`.

Bigger swings (all opt-in, none block the core path): LLM category
suggestion via the Claude API, an outbound status-change webhook, or a
generated SDK. Keep LLM features behind a setting and degrade
gracefully when unconfigured. Community clients get listed in the
registry — recognition is the currency.

## Opening the pull request

The full eight-step guide (fork → review) is in
[CONTRIBUTING](../CONTRIBUTING.md#your-first-pull-request-step-by-step).
Short version: branch, keep the gauntlet green, Conventional Commits
(`feat(api): …`), open the PR — CI checks style, a maintainer reviews
intent.

---

*This onboarding map points at real files — if you find it out of date
with the code, fixing it is itself a great first PR.*
