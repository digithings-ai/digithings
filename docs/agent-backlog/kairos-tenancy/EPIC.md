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


## Agent delivery status (2026-08-30, post-#3180 + unlock re-scan)

**Verdict: NOT COMPLETE.** Full audit: [`COMPLETION_AUDIT.md`](COMPLETION_AUDIT.md) + `/opt/cursor/artifacts/kairos-epic-completion-audit.md`.

**Code:** all 12 WPs on `develop` (promotion #3141). Notifications [#3161](https://github.com/digithings-ai/digithings/pull/3161), schema align [#3177](https://github.com/digithings-ai/digithings/pull/3177), unlock docs [#3178](https://github.com/digithings-ai/digithings/pull/3178), cred-push status [#3179](https://github.com/digithings-ai/digithings/pull/3179), completion audit [#3180](https://github.com/digithings-ai/digithings/pull/3180) — **all merged** (develop tip `bf34c015`).

**Schema (`core`):** migrations **096–106** applied + stamped. Cutover **900 not applied**.

**Edge Functions (`core`):** `stripe-webhook` v3, `create-checkout-session` v1, `customer-portal` v3 ACTIVE (await Stripe secrets). `settings` **v11** ACTIVE — thin GitHub-raw pin (post-#3179). Auth smoke: missing/invalid JWT → `401` (`settings-v11-smoke.log`). Full monorepo 9-file bundle staged (`settings-deploy-final.json`); CLI/Management API need `sbp_` PAT. Supabase MCP has **no secrets tool**; project EF secrets still **unset**. No EF redeploy on docs-only #3180.

**Secrets (names only; re-scanned post-#3180):**
- **SET in VM `.env` / `.local/secrets/kairos.env`:** `DIGIQUANT_VAULT_MASTER_KEY`, `DIGIQUANT_VAULT_KEY_ID`, `APP_URL`, `NEXT_PUBLIC_APP_URL`.
- **No new nonempty secrets** vs prior turn. Captcha/signup walls **not** re-burned.
- **Cursor env:** `SUPABASE_ACCESS_TOKEN` = JWT (not `sbp_`) → Management API **403**. Mailgun MCP ready but `MAILGUN_*` / `NOTIFY_FROM` **empty** — no Agent Mail smoke.
- **Still blocked:** Stripe TEST, Mailgun key+domain, Auth providers, Alpaca OAuth/keys, `sbp_` PAT, IBKR vendor, legal. Vault key **not** on EF secrets.
- **Review gate:** several Kairos merges lack `reviewed:agent` / hatch — document in audit; required before `main` promote.

**Acceptance evidence (agent-reachable; `/opt/cursor/artifacts/`):**
- House olympus unit: **420 passed** (`house-olympus-unit.log`).
- Chain integration refresh: **2 passed** (`kairos-chain-integration-refresh.log`).
- Kairos router/sync unit refresh: **67 passed** (`kairos-router-unit-refresh.log`).
- Live venue gates refresh: **8 passed** (`live-venue-gates-refresh.log`).
- Olympus tier Vitest refresh: **42 passed** (`olympus-tier-gates-refresh.log`).
- Settings EF smoke: `401` / `401` (`settings-v11-smoke.log`).
- RLS proof: **59/59 PASS** (`rls_isolation_proof.log`).
- E2E staging paper chain: **BLOCKED** — not faked.

**Pages promote (`develop` → `main`):** human release-gate (auth flag off; cutover 900 inert).

**Do not mark epic complete** until E2E + human/legal/IBKR gates clear.
