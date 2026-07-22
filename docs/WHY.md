# Why PleaseFix?

Malaysia already has official complaint channels — SISPAA (Sistem
Pengurusan Aduan Awam, the government's public-complaint system),
local-council (Pihak Berkuasa Tempatan, PBT) ticket
systems, agency hotlines. PleaseFix is not another complaint inbox. It is
the **public, community-owned issue tracker** that official channels
structurally cannot be.

## The problem with official channels

**They pass the buck.** Official systems close tickets on *their* terms —
most commonly "not our jurisdiction" or "that's a private company", and
the case is closed whether or not anything got fixed.

A real, typical issue:

> *"I cannot cross the road from the LRT station because of a barrier."*

- **Official route:** file with one agency → "not our jurisdiction /
  private company" → **closed**. The barrier is still there.
- **PleaseFix route:** one open, public record tracking every parallel
  filing — SISPAA: rejected; the Subang Jaya city council: filed;
  Prasarana (the public-transport operator): filed; raised with
  the local councillor — and the issue **stays open until it is actually
  fixed**, no matter how many agencies close their end of it.

**They are silos.** .gov.my systems are one-agency-deep. Cross-cutting
problems get handled — when at all — by creating entire institutions
(SPAD existed specifically to coordinate KTM, Prasarana, ERL, local
councils, and private bus operators) or ad-hoc joint task forces.
Citizens can't summon a task force. PleaseFix is **cross-jurisdictional
by design**: one issue, many agencies, many filings, one public status.

**They are private.** An official complaint is a conversation between one
complainant and one agency. Nobody else can see it, add to it, or
challenge its closure.

## What PleaseFix does differently

- **Everything is public.** Every issue is a shared community record.
  Anyone can see it, contribute photos and updates, follow up — including
  on issues an agency already "closed".
- **Public evidence is accountability.** It has happened that a council
  closed tickets as done when the contractor had done nothing. A public
  tracker captures the trail — dated photos, the dates each complaint was
  lodged and with whom — permanently. The record outlives the agency's
  ticket. That is the point.
- **Issues can be goals, with dependencies.** Citizens have goals, not
  category codes: *"I can't walk from A to B"* is blocked by *"no
  crossing at Y"* and *"streetlights out at Z"* — each possibly a
  different agency's problem. Government systems cannot represent "I want
  to walk from A to B". PleaseFix models blocking/blocked-by links
  between issues.
- **Community metadata.** Issues carry tags beyond any agency taxonomy —
  accessibility/a11y, CEDAW, public transport, environmental — enabling
  views no official system supports ("all accessibility issues in
  Subang").
- **It teaches jurisdiction.** Who is responsible for what is tribal
  knowledge in Malaysia. PleaseFix doubles as public guidance —
  jurisdiction explainers per issue type and area — and records official
  reference numbers (SISPAA, agency tickets) on each issue so the
  official trail is trackable from the public one.

**In one line:** FixMyStreet for Malaysia = public tracker +
jurisdiction education, with official system reference numbers attached —
the citizen-side coordination layer the official channels don't provide.

## Why open source, and why you

The platform is built in the open, on a deliberately contributor-friendly
stack (Django, HTMX, one `docker compose up`), with a public API designed
so that **third-party clients are first-class citizens** — build your own
reporting app, neighbourhood dashboard, or advocacy view on top of the
same public data. See [CONTRIBUTING.md](../CONTRIBUTING.md) and
[DESIGN.md](DESIGN.md).
