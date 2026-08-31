# Kairos + Alpaca finalize — gap audit (2026-08-30)

**Verdict: NOT COMPLETE** — do not mark the epic complete. Code gates for
creator / free-teaser / FX Hub land in this turn; staging E2E and vendor secrets
remain blocked.

## Product rules (this turn — authoritative)

| Rule | Status in code |
|------|----------------|
| Creator (GitHub / `chris.stefan@proton.me`) gets baseline+Kairos without Stripe | **Implemented** — `entitlement_grants.plan_floor=custom` + settings EF effective tier |
| Everyone else needs subscription for full product | **Documented + gated** — free teaser matrix; Custom writes require paid or grant |
| Free = teaser (digest summary + portfolio glimpse); no brokers/automations | **Implemented** — `digest_summary` / `portfolio_teaser` classes; brokers stay Custom+ |
| FX Hub = creator + email allowlist | **Implemented** — `client_product_grants` + nav/page/`ClientProductGate` |
| General client-product gate | **Plumbing** — same table + UI gate for future products |
| SETTINGS-IA / D1 amended (supersede baseline-broker tension) | **Done** |

## Spec WPs (K0–K5 / T0–T5) vs `develop`

| WP | Code on develop | Remaining gap |
|----|-----------------|---------------|
| K0 contracts | Landed | — |
| K1 Alpaca adapter | Landed | Live OAuth app / paper keys blocked on Turnstile |
| K2 IBKR read-first | Landed | Vendor onboarding human pole |
| K3 vault | Landed + EF settings | Needs Alpaca secrets for real connect |
| K4 router + mirror | Landed | Staging chain needs broker + Stripe |
| K5 notify | Landed; Mailgun loud-fail | `MAILGUN_*` secrets |
| T0 workspaces/RLS | 096–098 + 107 | Cutover **900 not applied** (intentional) |
| T1 Auth | GitHub proven on prod Pages | Google optional / disabled on core |
| T2 Stripe | EF + migrations | Captcha / price ids missing |
| T3 Settings | Landed (#3247 / Pages #3251) | — |
| T4 overlay | Landed | Needs Custom tier + BYOK in staging |
| T5 UI matrix | Landed; **extended** this PR | Apply mig 108 on `core` |

## Deploy / API setup gaps

| Item | Status |
|------|--------|
| Migrations 096–107 on `core` | Applied |
| Migration **108** (grants) | **This PR — apply on `core` after merge** |
| Cutover 900 | **Do not apply** without human approval |
| Draft promote #3183 | Leave draft |
| Settings EF | ACTIVE; needs redeploy after access.ts change |
| `STRIPE_*` / `MAILGUN_*` / `ALPACA_OAUTH_*` | **Still empty** — captchas |
| Staging E2E `scripts/kairos_staging_e2e.py` | Exit 2 until secrets land |

## Human asks (blocking)

1. **12x FX Hub access** — creator email is already seeded. Remaining teammates either (a) get an ops INSERT into `client_product_grants` or (b) redeem the hashed invite (`FX_HUB_INVITE_HASH` + migration 112) after signing in. Do not ship a login-optional shared secret.
2. **Vendor captchas** for digithings@ onboarding: Stripe hCaptcha, Mailgun reCAPTCHA, Alpaca Turnstile.
3. After secrets: `supabase secrets set` + redeploy billing/settings EFs; re-run staging E2E.
4. Confirm whether creator `plan_floor` should stay `custom` (ops / Kairos) or drop to `baseline` once Stripe works for self-serve.

## This PR deliverables

- `digiquant/supabase/migrations/108_entitlement_grants_and_products.sql`
- EF `_shared/access.ts` + settings effective-tier gate + Deno tests
- Dashboard entitlements free-teaser + `access.ts` / hooks + FX Hub UI gate
- SETTINGS-IA + D1 amend + SCHEMA.md
- Gap artifact: `/opt/cursor/artifacts/kairos-alpaca-finalize-gap.md`

## Explicitly not done

- Marking epic complete
- Applying cutover 900
- Merging draft #3183
- Obtaining Stripe / Mailgun / Alpaca API secrets without human captcha
