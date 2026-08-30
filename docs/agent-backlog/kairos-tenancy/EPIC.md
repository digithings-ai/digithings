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
- [x] RLS proof (pre-cutover harness vs canonical 001–105 + staged 900: 61/61; post-T1 anon-drop still human §6): user A cannot read user B's private rows on any tenant table; anon reads zero private rows post-T1.
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


## Agent delivery status (2026-08-30)

**Code:** all 12 WPs merged to `develop` (promotion #3141).

**Schema (`core`):** migrations 096–105 applied + stamped in `olympus_schema_migrations`. Cutover 900 **not** applied.

**Edge Functions (`core`):** `stripe-webhook`, `create-checkout-session`,
`customer-portal` ACTIVE (code deployed; runtime awaits Stripe secrets).
`settings` ACTIVE with full `_shared` sources (v3+); `PATCH /notifications`
writes `notification_prefs` once this PR lands and is redeployed. Runtime still
needs vault / Alpaca / `APP_URL` secrets. `prices-live` pre-existing.

**Olympus build:** green (flag off, static export check).

**Acceptance evidence:**
- House regression: `pytest -m unit tests/dq/olympus/ tests/dq/brokers/ tests/dq/notify/ tests/integration/test_kairos_tenancy_chain.py` → 659 passed (artifact `house-regression-acceptance.log`).
- Live venue gates: kairos router live/kill probes → 4 passed (`live-venue-gates.log`).
- RLS isolation harness: 61/61 PASS against canonical chain (`rls_isolation_proof.log`).
- E2E staging (signup→subscribe→Alpaca→overlay→fill→digest): **blocked** on human secrets (§ Human-owned prerequisites).

**Human blockers (unchanged):** Stripe test keys/prices/webhook secret, Mailgun, Auth providers (Google+GitHub), `DIGIQUANT_VAULT_MASTER_KEY`, Alpaca OAuth app, IBKR vendor email, legal read before live epic.
