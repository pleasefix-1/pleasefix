# Abuse resistance without logins

PleaseFix deliberately has no login wall: the report comes first. That
makes abuse handling a design problem, not an afterthought. This
document describes what exists now and where it goes.

## Principles

- **Hide, never delete.** Moderated content gets `is_hidden=True` and
  disappears from every public surface (pages, API, shortlinks) but
  stays in the database — auditable, reversible, and evidence if the
  abuse itself needs reporting.
- **Fail silently at abusers.** The honeypot pretends success; a
  soft-banned submitter (future) will see their content "posted" but
  hidden. Error messages that reveal the defense teach bots to evade it.
- **No PII for enforcement.** Submitter IPs are stored only as salted
  hashes (`sha256(secret + ip)`) — enough to throttle, dedupe flags,
  trace a spam wave, and later ban, without keeping addresses (PDPA).

## What exists now (seed)

| Layer | Mechanism | Where |
|---|---|---|
| Bots | Honeypot field on report + update forms; filled → silent drop | `core/forms.py`, `core/abuse.py` |
| Floods | Per-IP fixed-window throttles (limits in `settings.THROTTLE_LIMITS`), fail **closed** if the cache errors. The client IP is `REMOTE_ADDR` unless `TRUSTED_PROXY_COUNT>0` — **X-Forwarded-For is not trusted by default**, so it can't be spoofed to forge identities. Requires a shared cache (Redis) in production. | `core/abuse.py`, views |
| Bad content | "Report abuse" on every issue and update, no login; flags deduped per IP-hash; **3 distinct flags auto-hides** pending review | `Flag` model, flag views |
| Review | Admin: hidden filters, unhide action, flag list; hidden content excluded from all public queries via `Issue.public()` | `core/admin.py` |
| Trust | **Reporter secret** issued once per report (stored salted-hashed): verifies follow-ups ("✓ original reporter" badge) and claims the report into an account after login. Claimed reports and verified updates need 5 flags to auto-hide instead of 3 — verified identity buys flag-bomb resistance | `Issue.claim_token_hash/owner`, `core/views.py` |
| SSRF | URL-import fetches: http(s) only; DNS validated (all resolved addresses must be global) and **pinned** for the request against rebinding/TOCTOU; redirects re-checked per hop; body streamed with a per-chunk size cap | `core/importers.py` |

## Known gaps / next steps (roughly in order)

1. **Soft-ban list** keyed on ip_hash / email / phone (when identity
   lands): submissions confirm-then-hide instead of erroring. Domain-level
   email bans; `safe` allowlist override. (FixMyStreet's `abuse` table.)
2. **Flag-count gaming**: 3 flags is also a censorship button — a
   coordinated trio can hide a legitimate report. Mitigations queued:
   flags from throttled/new IP-hashes weigh less, auto-hide only pauses
   *public* visibility (reporter's tokenized link still works), admin
   notification on every auto-hide, and unhide restores with flag
   immunity until re-reviewed by staff.
3. **Geo-targeted CAPTCHA** (Turnstile) for non-MY connections only —
   zero friction domestically, kills offshore comment spam.
4. **Progressive identity as the real backstop**: the reporter-secret →
   claim flow is the first rung (done); next, phone/email verification
   unlocks higher limits and unverified submissions become
   `unconfirmed` (invisible until a confirm-click) once notifications
   land. Verification cost is the durable anti-abuse currency.
5. **Moderation snapshots**: staff edits preserve original content with
   a required reason + audit log (before any staff editing ships).
6. **Photo hygiene**: EXIF GPS stripping on upload (privacy), image
   re-encoding (kills embedded payloads), perceptual-hash dedupe.
7. **Rate-limit the OTP/SMS endpoints before they exist** — SMS is paid;
   OTP flooding is a billing attack.
