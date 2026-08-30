# Kairos epic — completion audit (GitHub Auth proven, 2026-08-30T21:18Z)

**2026-08-31T01:16Z Observer write-gate hop:** live `settings` EF vs free JWT — GET profile/notifications/brokers/keys **200**; `PATCH /notifications` **200**; `PATCH /profile` + `POST /brokers/connect` + `POST /keys/connect` **403 `TIER_FORBIDDEN`**. Ops-custom oauth connect **`OAUTH_NOT_CONFIGURED`**. Overlay `not_entitled` skip in-process; `job_runs` on `core` = 0. Staging E2E still exit **2**. Evidence: `/opt/cursor/artifacts/kairos-observer-tier-gate.md`.

**Verdict: NOT COMPLETE** — do not mark goal complete. Staging E2E still blocked on vendor captchas / secrets.

**2026-08-30 product-gates follow-up:** creator/ops `entitlement_grants` + free-teaser + FX Hub
`client_product_grants` implemented on branch `cursor/kairos-product-gates-3d52` (migration 108).
Full gap: [`KAIROS-ALPACA-FINALIZE-GAP.md`](KAIROS-ALPACA-FINALIZE-GAP.md) and
`/opt/cursor/artifacts/kairos-alpaca-finalize-gap.md`. Still **not** epic-complete.

Full artifact: `/opt/cursor/artifacts/kairos-github-auth-prod-proof.md`  
Human ask: `/opt/cursor/artifacts/HUMAN-CAPTCHA-ALL-VENDORS.md`  
Prior vendor recheck: `/opt/cursor/artifacts/kairos-completion-audit-vendor-recheck.md`  
Captcha-ask docs: [#3239](https://github.com/digithings-ai/digithings/pull/3239) merged into `develop` (superseded here with GitHub proof refresh).

## Summary

| Gate | Status |
|------|--------|
| Identity | **digithings** ([#3236](https://github.com/digithings-ai/digithings/pull/3236) merged) |
| Stripe / Mailgun / Alpaca API secrets | **MISSING** — captchas (forms re-filled digithings@) |
| Core EF vendor secrets | **not set** (vault / APP_URL / SUPABASE_* only) |
| Staging E2E | exit **2** — 9 named secrets (`kairos-staging-e2e-vendor-recheck.log`) |
| Mailgun notify loud-fail | exit **2** — `MAILGUN_NOT_CONFIGURED` |
| Olympus Auth Pages (#3231) | live on prod Pages |
| **GitHub Auth login** | **PROVEN** on `digiquant.io` + `core` DB |
| mig 107 personal workspace | **fired** for GitHub user (`plan_tier=free`, owner) |
| Email/password on login UI | **absent** (Google + GitHub only) — cannot use digithings@ Agentmail password path |
| Draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) | left draft |
| Cutover `900` | **not applied** |

## GitHub Auth — prod evidence (no secrets)

Project `rwagjbkvxkdwqmouagad` (`core`), PAT label **digithings**:

| Fact | Value |
|------|-------|
| `auth.users` count | **2** |
| Providers | **1× github**, **1× email** |
| GitHub user id | `0408ba97-caba-44d3-b2d0-5690ab5160a9` |
| GitHub email | `chris.stefan@proton.me` |
| GitHub login | `chrizefan` |
| Created / last sign-in | `2026-08-30T21:14:44Z` / `2026-08-30T21:15:48Z` |
| Personal workspace | `4700ff6e-…` slug `u-0408ba97caba44d3b2d05690ab5160a9` |
| Membership | owner |
| `plan_tier` | `free` (default; not Stripe-sourced) |
| Trigger | `on_auth_user_created_ensure_workspace` enabled; row timestamps match user insert |
| Bootstrap fix | **not needed** |

Unauth smoke: `https://digiquant.io/olympus/login` → **308** → `/olympus/login/` **200** (Continue with Google / Continue with GitHub).

Authed browser (agent desktop session still open): sidebar shows GitHub user email + Sign out; `/olympus/settings/` data source `rwagjbkvxkdwqmouagad.supabase.co`.

## Secrets obtained (names only)

None of the staging-required vendor API secrets. Present locally (not EF vendors): `digithings-supabase-pat`, `digithings-github-oauth.env`, signup password files only.

## Captcha still needed?

**Yes — all three.** Reply `Stripe captcha done` / `Mailgun captcha done` / `Alpaca turnstile done` after solving in open Cloud Agent browser tabs (do not close sibling vendor tabs).

## Next steps (staging E2E)

1. Human solves vendor captchas → agent writes `digithings-*.env` + EF `secrets set`.
2. Re-run `scripts/kairos_staging_e2e.py` (expect exit 0 once secrets land).
3. Optional: elevate a test workspace `plan_tier` only via documented ops path — GitHub user’s personal WS stays `free` until Stripe checkout.

## Docs branch

`cursor/kairos-github-auth-proof-3d52` — compare  
https://github.com/digithings-ai/digithings/compare/develop...cursor/kairos-github-auth-proof-3d52
