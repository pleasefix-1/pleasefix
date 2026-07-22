# Good first issues

Small, self-contained tasks that are a good way to learn the codebase.
Each names the files you'll touch and how to know you're done. Pick one,
say so on the tracker so nobody doubles up, and open a PR — the
step-by-step guide from fork to review is in
[CONTRIBUTING](../CONTRIBUTING.md), the role tracks are in
[TRACKS.md](TRACKS.md), and the walkthrough of how everything fits
together is [WALKTHROUGH.md](WALKTHROUGH.md) (interactive versions of
both live under `/site/` on any running instance).

These are suggestions, not assignments — the culture is stone soup
(see CONTRIBUTING): informal, no grand roadmap, scratch your own itch.
If none of these is your itch, build the thing you actually want.

Difficulty: 🟢 gentle · 🟡 moderate · 🔴 meaty.
Every task must keep `make check`-equivalent green: `ruff`, `mypy`,
`pytest`, `lint-imports`, and BM+EN strings translated.

## Frontend / HTMX / templates

- 🟢 **Consolidate inline CSS into a static stylesheet.** Every template
  has its own `<style>` block and some rules are copied (`.status`
  pills, input styling). Move shared CSS to `static/css/site.css`,
  load it once in `templates/base.html`.
  *Done when:* pages look identical, no inline `<style>` remains, CSS is
  served from `/static/`.
- 🟡 **Make the "report abuse" and update forms use HTMX.** `django_htmx`
  and `htmx.min.js` are already wired but unused. Post the flag/update
  via `hx-post` and swap just the affected fragment, keeping the no-JS
  form fallback.
  *Files:* `templates/issues/detail.html`, `core/views.py` (return a
  partial when `request.htmx`). *Done when:* flagging/updating doesn't
  full-page reload with JS on, and still works with JS off.
- 🟢 **Localize the allauth "(optional)" field suffix.** On `/accounts/
  signup/` the email label shows "(optional)" in English under BM.
  *Files:* `locale_vendor/ms/LC_MESSAGES/django.po`. *Done when:* signup
  in BM shows no stray English.
- 🟢 **Add an empty-state illustration / better copy to `/issues/`** when
  there are no reports yet.

## Backend / Django + GeoDjango

- 🟢 **Reddit comment-permalink import.** `core/importers.py` extracts the
  *post* even when the URL points at a specific comment. Read the
  comment when the permalink has a comment id.
  *Done when:* a comment URL imports the comment's text; a test covers it.
- 🟡 **First Celery task: strip EXIF + downscale uploaded photos.** Celery
  is configured but has no tasks. Add `core/tasks.py` with a task that
  processes `IssuePhoto` on save (privacy: EXIF GPS leaks location).
  *Done when:* an uploaded photo is re-encoded without EXIF; task is
  tested with a synchronous eager runner.
- 🟡 **`/api/v1/status` + cached front-page counters.** Add a machine-
  readable totals endpoint (issues, updates) and cache the homepage
  count so it isn't a `COUNT(*)` per request. *Files:* `api/v1.py`,
  `core/views.py`. *Done when:* endpoint returns totals; homepage count
  is cached.
- 🔴 **Nearby-issues query.** Add `GET /api/v1/issues/nearby?lat=&lon=&r=`
  using PostGIS distance (`core/models.py` manager method, ORM only).
  *Done when:* returns public issues within `r` metres, newest first,
  with a test using two points.

## AI / API / integrations

- 🟡 **Build a sample API client.** A tiny script or notebook that lists
  issues and submits one against the local API — lives in a new
  `examples/` dir, documented in the README. Great for learning the API
  surface. *Done when:* `python examples/list_and_report.py` works
  against `docker compose up`.
- 🔴 **LLM category suggestion (spike, opt-in).** Given an issue title +
  description, suggest a category via the Claude API. Must be behind a
  setting/flag, degrade gracefully when unconfigured, and never block
  submission. See `docs/DESIGN.md` §1 (categories are data). *Done when:*
  a management command prints a suggestion for a seeded issue; no hard
  dependency added to the default path.
- 🟡 **Webhook on issue status change.** A minimal outbound webhook
  (event log → POST) so third-party clients don't poll. *Done when:*
  configuring a URL delivers a signed JSON payload on status change,
  with retries via Celery.

## Housekeeping

- 🟢 **Raise test coverage on the importer's Reddit-403 branch and the
  OAuth-token path** (`core/importers.py`) — currently untested.
- 🟢 **Rename `ImportError_`** (trailing underscore) to `ImportFailed`
  across `core/importers.py` + callers.

---

*Keep this list current:* when you finish one, delete it here in the same
PR. When you spot another self-contained task, add it with the same
shape (difficulty · what · files · done-when).
