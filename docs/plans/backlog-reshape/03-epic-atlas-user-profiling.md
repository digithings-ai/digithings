# Epic: Atlas user profiling via DigiChat intake

**Title:** `[Epic] Atlas user profiling — intake, preferences, and profile-driven custom research`

**Labels:** `epic`, `component:root`, `priority:high`, `type:feature`

## Goal

Users sign in, go through a DigiChat intake session that builds a baseline investment profile, and then see Atlas content that reflects **their** preferences: their risk tolerance, horizon, asset preferences, custom universe, and research interests. Atlas becomes personalized rather than a single global feed.

This is the second major deliverable after the initial public Atlas ship — it turns Atlas from a demo into something a user would return to.

## Dependencies

- **Hard blocker:** Atlas daily-update backend must ship first (epic above).
- **Hard blocker:** DigiKey SSO federation (#175) — needs user identity to persist profiles.
- **Soft dependency:** DigiChat working on digithings.ai (#266, #261, #204) — the intake surface.

## Child tasks (to be filed as agent-tasks)

### Profile schema and persistence
1. **NEW** — Define investment-profile schema (Pydantic v2) — risk tolerance, horizon, liquidity, ESG, excluded sectors, base-currency, tax jurisdiction (coarse), experience level. Versioned.
2. **NEW** — Asset preferences schema — custom universe (tickers/ETFs), watchlists, exclusion lists.
3. **NEW** — Profile persistence: storage backend (DigiStore once landed, or DigiKey side-table in the interim), per-user-scoped, revisable.
4. **NEW** — Profile claims surfaced on DigiKey JWTs (minimal set: `profile_version`, `profile_id`) — per #209 pattern.

### DigiChat intake flow
5. **NEW** — DigiChat intake sub-graph (DigiGraph) — guided conversation that elicits profile fields via structured outputs (Pydantic v2), with clarifying follow-ups. Writes the profile on completion.
6. **NEW** — DigiChat UI: "Set up your profile" entry CTA, progress indicator, review-and-edit screen pre-submit.
7. **NEW** — Profile revision flow: user can re-enter intake or edit fields directly post-initial-setup.

### Profile-driven Atlas behavior
8. **NEW** — Atlas reads the logged-in user's profile and filters/ranks its daily outputs accordingly (universe filter + preference-weighted ranking).
9. **NEW** — Custom research trigger: user can request a one-off research run scoped to their profile + a prompt; run is queued, executed, and delivered back in Atlas or via email/notification.

## Non-goals

- Multi-profile households / shared accounts — v2.
- Real portfolio connection (Plaid, broker APIs) — separate epic.
- Tax-aware recommendations — requires professional review, explicitly out.
- Quant strategy personalization (Kairos) — separate epic.

## Acceptance

- [ ] A new user can: sign in → complete a DigiChat intake → see Atlas content filtered to their profile, all in one session, without dev support.
- [ ] Profile is durable across sessions and devices.
- [ ] User can revise the profile and see Atlas output shift accordingly within one daily cycle.
- [ ] Profile schema is versioned; migration path for schema v1 → v2 is documented.
- [ ] Legal/compliance review of intake questions and disclaimers (flag for human — not blocker for dev work, but blocker for public launch).

## Open questions

- Where does the profile live? DigiStore (once it exists) or a DigiKey-adjacent table? Recommend: DigiKey-adjacent during build, migrate to DigiStore when standalone module lands (#172).
- Do we treat the profile as PII subject to extra redaction in audit logs? Probably yes. Confirm with `digibase.audit.redact_mapping` pattern.
- How coarse-grained is the intake? Target: 5–8 minute conversation, not a 40-question questionnaire.

## Why this epic exists

Stated as the next-step deliverable after public Atlas ship: user-level access, profiling, preferences, custom research, custom asset preferences, custom investment profiling — "so that we could have users come in get profiled with a DigiChat session, to build their baseline set of preferences." Previously absent from the backlog entirely.
