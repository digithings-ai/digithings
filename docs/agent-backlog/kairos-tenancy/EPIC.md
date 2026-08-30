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
- [x] RLS proof (local harness vs canonical 001–110 + staged 900 A2 membership-only: 59/59 2026-08-31; 109 house teaser is pre-cutover only; 110 narrows anon private-book reads to house so overlay persist cannot leak; post-T1 anon-drop on `core` still human §6): user A cannot read user B's private rows; anon reads zero private rows post-900; free JWT sees 0 house weights/NAV/fills. Never apply 900 to `core` from this work.
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
production cron CLIs, remaining-hop proofs from Settings product state, staged
900 §A2 membership-only restore, and a fail-closed GHA **spec** (not installed:
`cursor/*` cannot write `.github/workflows/`).

**Schema (`core`):** migrations **096–110** applied (`110_anon_house_only_private_books`
narrows `anon_read` on private books to house; documents house+system). Live probe
2026-08-31: overlay doc visible to service (1) and hidden from `anon` (0); house
`positions` still 323 for anon. Cutover **900 not applied**. Local RLS harness
(throwaway DB + 001–110 + staged 900 A2): **pre-cutover 110 8/8 + post-cutover 59/59 PASS** (2026-08-31).

**Edge Functions (`core`):** `settings` **v29 ACTIVE** (`verify_jwt=true`, includes
`GET /jobs` `/fills` `/notifications/log`); checkout/portal await Stripe price
secrets (`PRICE_NOT_CONFIGURED`). EF secret **names** on core: vault + `APP_URL` +
Finnhub + platform `SUPABASE_*`. Still **no** `STRIPE_*` / `MAILGUN_*` / `ALPACA_*`.
`APP_URL` must be `https://digiquant.io` (not loopback). Checkout return URLs are
`/olympus/settings/?tab=billing`. `GET /settings/app-urls` is the Observer probe.

**Remaining hops (Observer JWT, re-audit 2026-08-31T05:11Z):** all five unproven.
`job_runs` / `broker_executions` / `notification_log` / `stripe_events` / BYOK
rows = **0**. One ops-custom workspace has an Alpaca **paper `api_key`** connection
(not OAuth; does not prove the remaining hop). House is `enterprise`/`active`
**without** Stripe ids — must not prove checkout. Overlay `--dry-run` against core
(after D1 `plan_floor` honor): `considered=5 targets=3 billing_active=1` — the
creator GitHub workspace (`plan_tier=free`, `plan_floor=custom`). Dry-run now
also prints `byok_present` (active credential rows among entitled targets; no
unseal). BYOK rows on that workspace are still **0**, so `--execute` would skip
`no_credentials`. Settings Pipeline / Brokers / Notifications tabs now read
`GET /jobs` `/fills` `/notifications/log` so skip reasons and empty remaining
hops are visible in the UI. Settings About shows the five remaining hops from
member-scoped reads (Observer-visible; digest log without inbox confirmation
stays unproven). Overlay persist is now **safe to enable after 110** (anon cannot
see overlay books; overlay publish skips `daily_snapshots`). Flag still **unset**
because BYOK rows = **0** — do not `--execute`. Seal resume path:
`python scripts/kairos_seal_byok.py` → exit **2** until gitignored
`digithings-byok.env` exists. Do not seal a placeholder; `--apply` only against
an overlay-entitled workspace (GitHub creator `plan_floor=custom`, not Observer
free, not house/system, not ops-custom `custom`/`none` without a grant).

**Cron CLIs (do not run `--all` / `--execute --all` on Observer or the api_key row):**
- Overlay `--check` / `--dry-run` **exit 0** when `CORE_SUPABASE_URL` +
  `CORE_SUPABASE_SERVICE_KEY` are in the process env (Cloud Agent env does not
  ship them; load from a gitignored PAT-fetched file for this VM only).
- Sync `--check` / `--dry-run` **exit 0**; dry-run `runnable=1` is the ops-custom
  Alpaca **api_key** paper row — do not poll/execute it (oauth hop still unproven).
- Combined `kairos_cron_check.py` still **exit 2** — Mailgun names empty. Overlay
  + sync store probes pass once `CORE_SUPABASE_*` are set.
- House GHA must still splice `pipeline-olympus-mailgun.env.yml` on a `chore/` /
  `feat/` branch. Scheduled probe spec still not installed under `.github/workflows/`.

**Auth (`core`):** GitHub Enabled + Email Enabled; **Google Disabled**. Mailgun MCP
still auth-fails. Canonical inbox `digithings@agentmail.to` has no vendor API-key mail.

**Harness:** `python scripts/kairos_staging_e2e.py` → exit **2** (9 named vendor secrets).
`python scripts/kairos_apply_vendor_secrets.py` → exit **2** until the three
gitignored `digithings-{stripe,mailgun,alpaca}.env` files exist (then `--apply`
pushes names onto core EF secrets). `python scripts/kairos_seal_byok.py` → exit
**2** until `digithings-byok.env` exists. Observer Settings hops all ok. A fifth
personal workspace (`kairos-e2e-…+s3101@`, `plan_tier=free`) appeared on core;
it does not prove Stripe.

**Do not mark epic complete** until staging E2E + human/legal/IBKR gates clear.
Do not merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) /
[#3256](https://github.com/digithings-ai/digithings/pull/3256). Never apply cutover 900.
