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
- [ ] K0 — Kairos execution contracts
- [ ] T0 — Workspaces + RLS privacy boundary

Wave B (after K0)
- [ ] K1 — Alpaca paper adapter (policy gate: broker adapter)
- [ ] K2 — IBKR Web API read-first adapter (policy gate: broker adapter)
- [ ] T1 — Supabase Auth login (human gate: auth flow)

Wave C (K3 after K1)
- [ ] K3 — Broker credential vault (human gate: cryptography)
- [ ] T2 — Stripe plan tiers (human gate: webhook secret handling)
- [ ] T5 — Tier-gated Olympus UI

Wave D
- [ ] K4 — Order-intent router + broker mirror sync (after K1+K3)
- [ ] T3 — Settings: profile, brokers, notifications (after T1+K3)

Wave E
- [ ] K5 — Daily digest + holding-change email v0 (after K4)
- [ ] T4 — Overlay pipeline runs, private books (after T0+T2+K4)

## Program-level acceptance

- [ ] House pipeline regression: `pytest -m unit tests/dq/olympus/` behavior unchanged by every child PR.
- [ ] RLS proof: user A cannot read user B's private rows on any tenant table; anon reads zero private rows post-T1.
- [ ] E2E (staging): sign up → subscribe (Stripe test) → connect Alpaca paper → overlay run →
      order routed to paper venue → fill mirrored → digest email received.
- [ ] No live `submit_order` reachable without env flag + human-gated code path (test-pinned).

## Human-owned prerequisites (tracked here, not blocking child code)

- [ ] Alpaca Connect OAuth app registration submitted (long pole for product connect)
- [ ] IBKR OAuth 1.0a vendor onboarding email sent (longest pole; scope to include trading)
- [ ] Stripe test-mode products (Baseline, Custom) + webhook secret provisioned
- [ ] Mailgun API key fixed + sending domain confirmed
- [ ] Supabase Auth providers (Google, GitHub) enabled on `core`
- [ ] `DIGIQUANT_VAULT_MASTER_KEY` generated into deploy secrets
- [ ] Legal read on investment-adviser status before any live-cutover epic
