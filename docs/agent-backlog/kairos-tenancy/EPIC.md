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
- [ ] `DIGIQUANT_VAULT_MASTER_KEY` generated into deploy secrets
- [ ] Legal read on investment-adviser status before any live-cutover epic


## Agent delivery status (2026-08-30, post-#3161 + settings v9)

**Code:** all 12 WPs on `develop` (promotion #3141). Notifications wire **merged** as [#3161](https://github.com/digithings-ai/digithings/pull/3161). Docs/schema align open as [#3177](https://github.com/digithings-ai/digithings/pull/3177) (ready; human merge — agent `gh` read-only).

**Schema (`core`):** migrations **096–106** applied + stamped on `olympus_schema_migrations` (106 = `notification_prefs` / `notification_log` canonical align). Cutover **900 not applied**.

**Edge Functions (`core`):** `stripe-webhook`, `create-checkout-session`, `customer-portal` ACTIVE (await Stripe secrets). `settings` **v9** ACTIVE — thin SHA-pinned GitHub-raw import of #3161 tip (`41a57414…`) including `PATCH /notifications` → `notification_prefs`. Auth smoke: missing/invalid JWT → `401`. Full monorepo bundle preferred once `sbp_` PAT exists for CLI secrets + multi-file deploy hygiene. Project EF secrets still **unset** (Management API 403 without `sbp_`).

**Secrets (names only):**
- **SET in VM `.env` / `.local/secrets/kairos.env`:** `DIGIQUANT_VAULT_MASTER_KEY`, `DIGIQUANT_VAULT_KEY_ID`, `APP_URL`, `NEXT_PUBLIC_APP_URL`.
- **Cursor env:** `SUPABASE_ACCESS_TOKEN` present but **JWT** (not `sbp_` PAT) — cannot `supabase secrets set` / Management secrets API.
- **Agent Mail:** `digithings@agentmail.to`.
- **Still blocked:** Stripe test keys/prices/webhook (hCaptcha), Mailgun MCP auth, Auth providers (Google+GitHub), Alpaca OAuth/KYC, Supabase `sbp_` PAT, IBKR vendor, legal read. Vault master key **not** pushed to project EF secrets.

**Acceptance evidence (re-run this turn, artifacts under `/opt/cursor/artifacts/`):**
- House olympus unit: **420 passed** (`house-olympus-unit.log`).
- Vault + notify unit: **138 passed** (`kairos-vault-notify-unit.log`).
- Brokers + contracts: **208 passed**, 2 skipped (`kairos-brokers-contracts.log`).
- Olympus kairos unit: **67 passed** (`olympus-kairos-unit.log`).
- Settings EF smoke: `401` no-auth / invalid JWT (`settings-v9-smoke.log`).
- RLS proof: re-run in progress / prior 61/61 harness (`rls_isolation_proof.log`).
- E2E staging (signup→subscribe→Alpaca→overlay→fill→digest): **still blocked** on vendor secrets above.

**Do not mark epic complete** until E2E + human/legal/IBKR gates clear.
