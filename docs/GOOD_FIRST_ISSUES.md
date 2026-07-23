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

## The web map (a mini-track) 🗺️

The map is the most visible gap between PleaseFix today and "a real
issue tracker". These two tasks build the MVP in order; each is
shippable on its own. Design context:
[DESIGN.md](DESIGN.md) §1 ("Web map: provider-modular") — the basemap
is a **config value**, served by a free keyless tile host, and all map
plumbing lives in **one** wrapped component.

- 🟡 **Map 1: shared map component + pins on `/issues/`.**
  Creates the plumbing every later map page reuses, and proves it by
  showing reported issues as markers on the browse page.
  *Steps:*
  1. **Vendor MapLibre GL JS** (we vendor JS like
     `static/js/htmx.min.js` — never CDN `<script>` tags): download
     `dist/maplibre-gl.js` and `dist/maplibre-gl.css` from the latest
     [MapLibre GL JS release](https://github.com/maplibre/maplibre-gl-js/releases)
     into `static/js/maplibre-gl.js` and `static/css/maplibre-gl.css`.
  2. **Make the basemap style a setting.** In `config/settings.py`,
     inside the `env(...)` defaults block next to `MAP_CENTER_LAT`, add
     `MAP_STYLE_URL=(str, "https://tiles.openfreemap.org/styles/liberty")`,
     and next to the `MAP_CENTER = ...` line add
     `MAP_STYLE_URL = env("MAP_STYLE_URL")`. Add the variable to
     `.env.example` with a comment saying any MapLibre style URL works
     (OpenFreeMap is free and keyless — that's why it's the default).
  3. **Expose it to templates**: add
     `"MAP_STYLE_URL": settings.MAP_STYLE_URL` to the dict in
     `core/context_processors.py` (MAP_CENTER and MAP_DEFAULT_ZOOM are
     already there).
  4. **Write the wrapper, `static/js/map.js`** — the ONLY file allowed
     to mention `maplibregl`. On `DOMContentLoaded`, for every
     `.pf-map[data-map]` element, create a
     `new maplibregl.Map({container, style: el.dataset.style, center:
     [lon, lat], zoom})` from the element's `data-style`, `data-lat`,
     `data-lon`, `data-zoom` attributes, then dispatch a bubbling
     `pf:map` CustomEvent with the map in `detail` so page scripts can
     add markers without touching MapLibre setup themselves.
  5. **Load it only on map pages** (the bundle is ~800 kB — don't load
     it site-wide): add `{% block head_extra %}{% endblock %}` just
     after `{% block meta %}` in `templates/base.html`; map pages fill
     it with the two `<link>`/`<script>` tags (`{% static %}` paths,
     `defer` on scripts, `map.js` after `maplibre-gl.js`).
  6. **Pins on the browse page.** In `core/views.py::issue_list`, build
     a list of `{"lat": i.latitude, "lon": i.longitude, "title":
     i.title, "url": i.get_absolute_url()}` dicts (those model
     properties already exist) and pass it as `issue_points`. In
     `templates/issues/list.html`, render
     `{{ issue_points|json_script:"issue-points" }}` plus a
     `<div class="pf-map" data-map data-style="{{ MAP_STYLE_URL }}"
     data-lat="{{ MAP_CENTER.lat }}" data-lon="{{ MAP_CENTER.lon }}"
     data-zoom="{{ MAP_DEFAULT_ZOOM }}"></div>` (give it a height in
     CSS — a map div with no height renders as nothing, the classic
     gotcha). For the markers, teach `map.js` an optional
     `data-points="issue-points"` attribute naming the `json_script` id:
     when present, it reads the JSON and adds one marker per point, with
     a popup linking `title` to `url`. That keeps every `maplibregl.*`
     call inside `map.js`, which is the rule.
  *Done when:* `/issues/` shows a map with a marker per listed issue
  that links to its page; the page still renders fine with JS off (the
  list is unchanged below the map); no CDN URLs anywhere; `MAP_STYLE_URL`
  changed in `.env` visibly swaps the basemap; the CI gauntlet passes.

- 🟡 **Map 2: click-to-set location on the report form.** (After Map 1.)
  Today `/report/` asks for raw latitude/longitude numbers. Add the map
  so people can just point at the problem.
  *Steps:*
  1. In `templates/issues/report_new.html`, fill the `head_extra` block
     (from Map 1) with the MapLibre + `map.js` tags, and add the same
     kind of `.pf-map` div inside the "Where is it?" field, keeping the
     latitude/longitude inputs — they are the no-JS fallback and the
     precision editor, so hide them only when JS has confirmed the map
     is up (progressive enhancement, same pattern as the existing
     "Use my current location" button in that template).
  2. In the page script (get the map from the `pf:map` event): on map
     `click`, place/move a draggable marker and write
     `lngLat.lat.toFixed(6)` / `lngLat.lng.toFixed(6)` into
     `#id_latitude` / `#id_longitude` (exactly what the geolocation
     button already does — read it first). On marker `dragend`, update
     the fields again. If the fields are prefilled (form re-render after
     a validation error, or URL-import prefill), start the marker there
     and center the map on it.
  3. Make the existing "Use my current location" button also move the
     marker and pan the map when the map is present.
  4. Any new visible strings go through `{% translate %}`; add the BM
     translation (`manage.py makemessages -l ms`, edit, `compilemessages`).
  *Done when:* clicking the map fills both fields and submitting works;
  dragging the marker updates them; the form still submits with JS
  disabled by typing coordinates; a validation-error re-render keeps the
  marker where the reporter put it; gauntlet passes.

Not in these tasks (design-noted for later, see DESIGN.md §1): overlay
layers for jurisdiction boundaries and the map-override data — the
component's `pf:map` event is the hook they'll use.

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
