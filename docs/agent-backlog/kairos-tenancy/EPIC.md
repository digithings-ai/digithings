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


## Agent delivery status (2026-08-30, post-#3186)

**Verdict: NOT COMPLETE.** Full audit: [`COMPLETION_AUDIT.md`](COMPLETION_AUDIT.md).

**Code:** all 12 WPs on `develop` (promotion #3141). Through audit refresh [#3186](https://github.com/digithings-ai/digithings/pull/3186) — **merged** (develop tip `b9e1e8e3`). Pending non-secret fix: GET `/profile` hydrate on `cursor/profile-get-hydrate-539c` (compare URL; `gh pr create` 403).

**Schema (`core`):** migrations **096–106** applied + stamped. Cutover **900 not applied**.

**Edge Functions (`core`):** billing EFs ACTIVE (await Stripe secrets). `settings` **v12** ACTIVE — thin GitHub-raw pin → `732a77d0` (GET `/notifications` + PATCH). Smoke 401 (`settings-v12-smoke.log`). Still no `sbp_` / no EF secrets push. Profile GET lands after parent merges hydrate branch + thin pin.

**Secrets (names only; re-scanned post-#3186):**
- **SET in VM:** `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL`.
- **No new nonempty secrets.** No captcha vendor signups. No EF push / Mailgun smoke.
- **Cursor env:** `SUPABASE_ACCESS_TOKEN` = JWT (`eyJ…`, not `sbp_`). Mailgun/Stripe/Alpaca/Auth keys empty or absent.

**Agent-reachable paper E2E (fakes/mocks — NOT live staging):** 145 passed — `kairos-e2e-paper-fakes-refresh.log` (tenancy chain + Alpaca + venue contracts + kairos router/sync + IBKR). Staging E2E still **BLOCKED**.

**Review gate (parent):** #3161 / #3184 / #3185 hatched. Bodies queued for #3141, #3177–#3181, #3186 under `/opt/cursor/artifacts/kairos-reviews/` (agent cannot comment/label — 403). Leave [#3183](https://github.com/digithings-ai/digithings/pull/3183) draft.

**Pages promote:** branch `cursor/promote-kairos-pages-3d52` pushed; human opens/merges when ready. Flag off; no cutover 900.

**Do not mark epic complete** until staging E2E + human/legal/IBKR gates clear.
