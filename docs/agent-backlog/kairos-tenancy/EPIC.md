<!-- title: [epic] Olympus client-ready: Kairos execution + user tenancy -->

## Goal

Ship the two remaining Olympus milestones so the product can take paying clients: **Kairos**
(paper-first broker execution: Alpaca connect, IBKR read-first) and **user tenancy** (Supabase
Auth login, Stripe tiers, private per-user books, overlay pipelines with BYOK, email digests).

Authoritative spec: `docs/superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md`
(decisions D1–D10 are locked there; do not re-litigate in child issues).

## Locked shape (summary)

- Tiers: Observer (free; Atlas + narrative, no weights/NAV) → Baseline (full house book, read) →
  Custom (overlays, private book, broker connect, BYOK) → Enterprise (manual).
- Payments: **Stripe** (ADR-0004). Identity: **Supabase Auth**; digikey untouched.
- Olympus stays a static export; enforcement = RLS + Supabase Edge Functions.
- Brokers: Alpaca OAuth2/paper first; IBKR OAuth 1.0a read-first, orders feature-flagged off.
- External venues: broker is authoritative; append-only mirror tables (`broker_*`); internal
  `portfolio_ledger_*` stays authoritative only for `paper_internal`.
- **No live trading in this epic.** Live cutover is a separate, human-gated epic.

## Child work packages

Wave A
- [x] K0 — Kairos execution contracts
- [x] T0 — Workspaces + RLS privacy boundary

Wave B (after K0)
- [x] K1 — Alpaca paper adapter (policy gate: broker adapter)
- [x] K2 — IBKR Web API read-first adapter (policy gate: broker adapter)
- [x] T1 — Supabase Auth login (human gate: auth flow)

Wave C (K3 after K1)
- [x] K3 — Broker credential vault (human gate: cryptography)
- [x] T2 — Stripe plan tiers (human gate: webhook secret handling)
- [x] T5 — Tier-gated Olympus UI

Wave D
- [x] K4 — Order-intent router + broker mirror sync (after K1+K3)
- [x] T3 — Settings: profile, brokers, notifications (after T1+K3)

Wave E
- [x] K5 — Daily digest + holding-change email v0 (after K4)
- [x] T4 — Overlay pipeline runs, private books (after T0+T2+K4)

## Program-level acceptance

- [x] House pipeline regression: `pytest -m unit tests/dq/olympus/` behavior unchanged by every child PR.
- [x] RLS proof (pre-cutover harness vs canonical 001–106 + staged 900: 59/59 this turn; post-T1 anon-drop still human §6): user A cannot read user B's private rows on any tenant table; anon reads zero private rows post-T1.
- [ ] E2E (staging): sign up → subscribe (Stripe test) → connect Alpaca paper → overlay run →
      order routed to paper venue → fill mirrored → digest email received.
- [x] No live `submit_order` reachable without env flag + human-gated code path (test-pinned).

## Human-owned prerequisites (tracked here, not blocking child code)

- [ ] Alpaca Connect OAuth app registration submitted (long pole for product connect)
- [ ] IBKR OAuth 1.0a vendor onboarding email sent (longest pole; scope to include trading)
- [ ] Stripe test-mode products (Baseline, Custom) + webhook secret provisioned
- [ ] Mailgun API key fixed + sending domain confirmed
- [ ] Supabase Auth providers (Google, GitHub) enabled on `core`
- [x] `DIGIQUANT_VAULT_MASTER_KEY` generated into deploy secrets
- [ ] Legal read on investment-adviser status before any live-cutover epic


## Agent delivery status (2026-08-31, remaining hops + cron CLIs)

**Verdict: NOT COMPLETE** — staging E2E still blocked on Stripe/Mailgun/Alpaca OAuth
captchas and Google Auth. All 12 WPs have code on `develop`. This branch adds
production cron CLIs and remaining-hop proofs from Settings product state.

**Schema (`core`):** migrations **096–109** applied (`109_authenticated_house_teaser_read`).
Cutover **900 not applied**.

**Edge Functions (`core`):** `settings` **v29 ACTIVE** (`verify_jwt=true`); checkout/portal
await Stripe price secrets (`PRICE_NOT_CONFIGURED`).

**Remaining hops (Observer JWT, 2026-08-31):** all five unproven. `job_runs` /
`broker_executions` / `notification_log` / `stripe_events` / BYOK rows = **0**.
One ops-custom workspace has an Alpaca **paper `api_key`** connection (not OAuth;
does not prove the remaining hop). House is `enterprise`/`active` **without**
Stripe ids — must not prove checkout.

**Cron CLIs (do not run `--all` on Observer until Stripe + BYOK + Alpaca OAuth land):**
- `python -m digiquant.olympus.overlay` — overlay_daily dispatch; hop proves on `succeeded` only
- `python -m digiquant.olympus.kairos.sync_cron` — Alpaca paper fill mirror
- `python scripts/kairos_cron_check.py` — combined `--check` (overlay + sync + Mailgun)

**Auth (`core`):** GitHub Enabled + Email Enabled; **Google Disabled**. Mailgun MCP still
auth-fails. Canonical inbox `digithings@agentmail.to` has no vendor API-key mail.

**Harness:** `python scripts/kairos_staging_e2e.py` → exit **2** (9 named vendor secrets).
Observer Settings hops all ok (`TIER_FORBIDDEN` on Custom writes).

**Do not mark epic complete** until staging E2E + human/legal/IBKR gates clear.
Do not merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) /
[#3256](https://github.com/digithings-ai/digithings/pull/3256). Never apply cutover 900.
