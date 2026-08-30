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
- [x] GitHub Auth provider enabled on `core` (Google still **Disabled**)
- [ ] Google Auth provider enabled on `core` + Cloud OAuth client redirect
- [x] `DIGIQUANT_VAULT_MASTER_KEY` generated into deploy secrets
- [ ] Legal read on investment-adviser status before any live-cutover epic


## Agent delivery status (2026-08-31)

**Verdict: NOT COMPLETE** (staging E2E still blocked on Stripe/Mailgun/Google Auth/Alpaca captchas + secrets). Full audit: [`COMPLETION_AUDIT.md`](COMPLETION_AUDIT.md).  
**Human checklist:** [`HUMAN-UNBLOCK.md`](HUMAN-UNBLOCK.md). Linked from [`DEPLOYMENT.md`](DEPLOYMENT.md).

**Auth Pages:** Prod `/olympus/login/` **200** (#3231). GitHub login proven. Email/oauth-first dress is **not** on Pages until [#3266](https://github.com/digithings-ai/digithings/pull/3266) merges to `main` (develop twin [#3264](https://github.com/digithings-ai/digithings/pull/3264)). Do **not** merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) or rolling promote [#3256](https://github.com/digithings-ai/digithings/pull/3256). Never apply cutover 900.

**Code:** all 12 WPs on `develop` + notify `MAILGUN_NOT_CONFIGURED` loud-fail CLI. Prior: `PRICE_NOT_CONFIGURED` / `OAUTH_NOT_CONFIGURED` + `scripts/kairos_staging_e2e.py`.

**Schema (`core`):** migrations **096–109** applied (107 ledger row stamped 2026-08-31 — function/trigger already live; 108 entitlement grants, 109 house teaser). Cutover **900 not applied**. Local RLS harness vs 001–109 + staged 900 **59/59** after [#3268](https://github.com/digithings-ai/digithings/pull/3268) (membership-only book SELECT post-cutover).

**Edge Functions (`core`):** `settings` **v27 ACTIVE**; `create-checkout-session` **v6 ACTIVE**; `customer-portal` **v7**; `stripe-webhook` **v6**. Billing EFs still loud-fail without Stripe secrets.

**Auth (`core`):** **GitHub Enabled** + Email Enabled; **Google Disabled**. Redirect allow-list includes `/olympus/auth/callback`. Checkout **`PRICE_NOT_CONFIGURED`**.

**Secrets (names only):**
- **`sbp_` path unlocked** — Management API lists **12** EF names (no vendor).
- Agentmail: **no** human-pasted Stripe/Mailgun/Alpaca/Google secrets.
- **Still empty / blocked:** Mailgun (MCP auth fail), Stripe, Google OAuth, Alpaca OAuth.
- **Waiting artifact:** `/opt/cursor/artifacts/kairos-WAITING-ON-SECRETS.json` → `PARTIAL_UNLOCK`.
- **Harness:** `python scripts/kairos_staging_e2e.py` → exit **2**; notify `--require-mailgun` → exit **2**.

**Closest real chain (NOT staging E2E):** Agentmail email signup + confirm → JWT → settings profile/notifications/brokers **200** + free personal workspace (107) → checkout **`PRICE_NOT_CONFIGURED`**. Prior: ops Custom (≠ Stripe) → vault seal. Staging signup→Stripe→Alpaca OAuth→overlay→digest still **BLOCKED**.

**Do not mark epic complete** until staging E2E (signup → Stripe → Alpaca paper → overlay → digest) plus Google Auth, legal, and IBKR vendor gates clear. Prod Auth Pages login route already smokes (#3231); email UI waits on #3266.
