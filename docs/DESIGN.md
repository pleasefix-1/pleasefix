# PleaseFix — Design & Decisions

Architecture and product decisions, with rationale. Motivation and
positioning live in [WHY.md](WHY.md). Section numbers (§) are referenced
from code comments and other docs.

## 1. Core stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend | **Django + GeoDjango**, Python, strict typing (mypy) from day one | Largest average-developer pool; GeoDjango is purpose-built for this domain; admin panel = moderation/ops backend for free; framework conventions police style; types are the first-pass review |
| Database | **PostgreSQL + PostGIS** (single database) | Spatial queries first-class; Postgres full-text search before reaching for Elasticsearch |
| Frontend | Server-rendered Django templates + **HTMX** (Alpine.js where needed) | Lowest contributor skill floor; one rendering path; the app is mostly forms + a map |
| Map | **MapLibre GL JS + PMTiles** (static file, no tile server); Nominatim for geocoding | No API keys or billing; PMTiles is a static file served with range requests; the map is wrapped in one well-documented component so contributors never touch tile plumbing |
| API | **django-ninja**, OpenAPI schema generated from typed code, versioned `/api/v1/` | Schema-first contract; the schema file is a reviewed artifact; CI fails on unintended API surface changes |
| Background jobs | Celery (+ Redis broker) | Notifications, image processing, dispatch |
| Object storage | S3 API via django-storages; **VersityGW bundled as the compose default** (§8) | The app speaks only "dumb S3" (put/get/presign/delete); backend swappable |
| Architecture | **Modular monolith** — no microservices | One `docker compose up` to contribute; boundaries enforced by import-linter in CI |

## 2. Explicit non-features

- **No cobrands / no multitenancy.** One brand, one behavior, one
  template set, one test matrix. If a second city/agency ever wants it:
  one deployment per customer (same image, separate DB, config-only
  differences). No `tenant_id` in the schema, ever. Discipline now: all
  deploy-specific values (brand, map center, boundaries, agency
  endpoints, locale) live in config/env, never as code literals.
- **No Open311.** No existing government systems here speak anything
  useful to us. If an Open311-consuming counterpart ever appears, it
  becomes one dispatch adapter among others.
- **Categories, workflows, and jurisdictions are data, not code** —
  admin-editable configuration rows (fields, routing, SLA timers,
  external category mappings). Anything that looks like it needs a code
  hook is attempted as config first.
- **Easy jurisdiction editing is a feature, not an afterthought.** Nearly
  every system in this space freezes jurisdiction data in imports or
  code, so misrouting can't be fixed by the people who spot it. PleaseFix
  ships a usable admin editor for boundaries and
  agency↔area↔category responsibility mappings.

## 3. Contribution architecture (blast radius)

- **Protected core** (maintainers only): report lifecycle, geo queries,
  auth, dispatch framework. **Contribution zones**: channel adapters
  (inbound + outbound), client templates, config, translations.
- Boundaries enforced mechanically: import-linter in CI; CODEOWNERS on
  core, migrations, and the OpenAPI schema.
- Migrations are maintainer-gated, always in their own PR
  (django-migration-linter).
- CI automates subjective judgment: auto-format (Ruff), lint, strict type
  check, coverage floor on changed lines, PR size limit.
- No raw SQL in contributions — ORM only; the few raw geo queries live in
  the core.
- Invariant test suite as tripwires ("closed never transitions to
  draft") + factories + golden-path suite.
- Runtime containment: feature flags; jobs with retries, idempotency,
  dead-letter queues; error reporting routed per module/adapter.
- Trust gradient: new contributors start in adapters/templates, earn inward.

## 4. Identity & signup

- **Progressive identity: the report comes first.** Anonymous-ish
  submission with just phone or email → shadow account → full account
  only when the user wants history/subscriptions.
- Multiple identities per account from day one (phone, social,
  MyDigital ID resolving to one person), with account merging.
- **django-allauth** for everything; MyDigital ID as a custom OIDC
  provider — a *verification level* on an account, never a login
  requirement.
- Phone/OTP via a swappable SMS gateway abstraction; outbound SMS status
  updates from launch ("your report was fixed").

## 5. Inbound channels — adapter pattern

- All intake (web form; later WhatsApp, SMS, agency email replies) goes
  through **inbound channel adapters** producing a normalized
  `IncomingReport` into one core intake service — the web form included,
  from day one.
- **Event log under everything**: every inbound webhook and outbound
  message persisted (raw payload, timestamps, status) before processing.
  Replay, audit, and "what happened to this citizen's report" in one
  table.
- Admin channel console: recent messages per channel, delivery status,
  failure reasons, resend.
- Dev ergonomics: fake adapters (fake WhatsApp = a form in the dev UI;
  OTP prints to console) so contributors never need Meta verification.
- **Import from a link, two ways.** Server-side import fetches a
  Reddit/X/Facebook/web URL and prefills the report form (SSRF-guarded).
  Because some platforms block server fetches (Reddit 403s datacenter
  IPs) and a browser can't fetch them cross-origin either (CORS),
  **browser-side import** runs in the reporter's own page context: a
  bookmarklet scrapes the current page, and the installable PWA registers
  as a share target — both deep-link into `/report/`'s query-param
  prefill. This dodges the block, uses the reporter's IP/login, and
  removes the server-fetch/SSRF surface for those paths.

## 6. Outbound dispatch — no existing gov integrations assumed

Reality: targets are email inboxes, WhatsApp groups, Excel workflows,
portals without APIs. Status flows back through humans.

- Typed **`DispatchAdapter`** interface; the framework owns retry,
  dead-letter, idempotency; adapter authors write only "send it".
  Per-adapter config schema editable in admin. This is the ideal
  contributor zone.
- **Email is the floor adapter and the reference implementation** —
  templated per-agency email with photos and map link, delivery tracked
  in the event log, bounces surfaced in admin.
- **Manual return path is a launch feature**: agency-liaison workflow in
  admin; unique short reference code on every dispatched report
  ("REF-4821 selesai" is unambiguous); inbound-email parser that at least
  files replies against the right report.
- **Community status ≠ official status.** Each official filing (agency,
  channel, reference number, date, *their* status) is a separate record
  attached to the issue — many per issue. An agency closing its ticket
  updates that filing; it never auto-closes the issue (see WHY.md).
- Agency-facing scoped portal view for agencies with no systems of their
  own — for them, we are the system.
- SISPAA integration is a ladder behind one adapter: manual liaison →
  form automation against SISPAA 1.0 → the SISPAA 2.0 gateway/API as
  access opens up. Category config carries a `sispaa_category` mapping.

## 7. The API is the product (stone soup)

The product for developers is the API plus a 15-minute path to a running
client. The first-party web app is just the reference client.

- One OpenAPI schema generated from typed code, versioned, reviewed as a
  repo artifact (`api/openapi.json`). Additive changes anytime; breaking
  changes only in `/api/v2` with dual-running.
- Generated SDKs (TypeScript, Python) regenerated in CI.
- Thin client templates in separate repos (SPA first, HTMX/BFF second —
  the latter extracted from this app). The first-party HTMX views and the
  API call one shared typed service layer, so dogfooding closes the
  contract-drift gap.
- Hosted public sandbox: always-on demo API, seeded Malaysian data,
  nightly reset, OTP echoed in response — client developers never need
  Docker or PostGIS.
- Webhooks for report status changes; CORS + rate limiting designed for
  browser-based third-party clients.

## 8. Infrastructure — single server, honest ops

- **Docker Compose is the production topology** (dev shares the same
  shape): app, worker, Postgres+PostGIS, Redis, VersityGW, Caddy
  (auto-TLS). PMTiles served by Caddy as a static file.
- 12-factor discipline despite the single server: config via env, no
  same-box assumptions. Every exit (second server, deploy-per-customer,
  managed hosting) stays a compose change.
- **VersityGW** as the S3 default: Apache-2.0, stateless single binary,
  and the killer ops feature — the posix backend means **photos are plain
  files**: rsync/restic-able, inspectable, recoverable without the
  gateway. Presigned URLs go through a public subdomain route in Caddy
  (never the internal container address); "SignatureDoesNotMatch → check
  the proxy" lives in the Caddyfile comments.
- RUNBOOK, off-box backups (the reports DB is the crown jewels),
  unattended updates, uptime + disk-space alerting, capped container log
  sizes — full disk from logs/photos is how single-server deployments die.

## 9. i18n

Bahasa Melayu + English from the first template — retrofitting
translation across a template codebase is the classic death march. All
user-facing strings go through gettext; notifications render in the
reporter's language; admin-editable config data (category and agency
names) gets its own translation strategy.

## 10. Next design steps

The detailed domain model (issues, updates, agencies, categories,
filings, dependencies, states, moderation) is the next design session;
`core/models.py` stays empty until it lands. A public gap analysis
against 15 years of FixMyStreet production experience informs it.
