# Kairos epic — completion audit (2026-08-30)

**Verdict: NOT COMPLETE** — do not UpdateGoal complete.

Agent run: https://cursor.com/agents/bc-c5b145ca-ac4a-56ed-ab78-919d4208ab35  
Develop tip at audit: `0f235935` (merge of #3179)  
Settings EF on `core`: **v11** ACTIVE (thin GitHub-raw pin to `0f235935…`)

---

## This-turn objective checklist

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Inspect develop vs #3179; merge if CI green | **PASS** | PR [#3179](https://github.com/digithings-ai/digithings/pull/3179) marked ready + merged (`0f235935`, 2026-08-30T16:00:32Z). Required CI + CodeQL green before merge. |
| 2a | Supabase MCP: secrets/env tools? | **FAIL / absent** | Full `GetDynamicTools(Supabase)` catalog: **no** secrets/env tools (only migrate/SQL/EF/branch/project). Cross-namespace search: no Supabase secrets tool. |
| 2b | Push `DIGIQUANT_VAULT_*`, `APP_URL`/`NEXT_PUBLIC_APP_URL` to project EF secrets | **BLOCKED** | Values **present** in VM env / `.local/secrets` (names only; not logged). Management API `GET /v1/projects/…/secrets` → **403** (JWT `eyJ…`, not `sbp_`). CLI deploy also rejects non-`sbp_` token. |
| 2c | Redeploy full settings monorepo bundle; smoke 401 | **PASS (thin fallback)** | Full 9-file payload prepared (`/opt/cursor/artifacts/settings-deploy-final.json`, content hash `2fc5f9bb62727c7c`). MCP `deploy_edge_function` **thin** pin to post-#3179 tip → settings **v11**. Smoke: `settings-v11-smoke.log` — GET no-auth **401**, POST invalid JWT **401**. Direct Management API / raw MCP HTTP blocked (403). |
| 3 | Mailgun MCP `mcp_auth` if `needsAuth` | **PASS (skip)** | `namespaceStatus: ready` — no auth attempt (per instructions). Captcha/signup walls not re-burned. |
| 4 | Completion audit + EPIC delivery update | **PASS** | This file + `docs/agent-backlog/kairos-tenancy/EPIC.md` delivery section. |
| 5 | Re-run stale agent-reachable proofs | **PASS** | Chain / tier / live-venue refreshed this turn (below). E2E paper **not** faked. |
| 6 | Branch `cursor/*-3d52`, push docs | **PASS** | `cursor/kairos-completion-audit-3d52` (compare URL in PR notes). |
| 7 | Goal complete? | **FAIL** | Epic end-state still blocked on human/vendor secrets + E2E. |

---

## EPIC.md — child work packages (Wave A–E)

| WP | Status | Evidence |
|----|--------|----------|
| K0 contracts | **PASS** | On `develop` via promotion #3141; unit coverage in brokers/contracts + kairos. |
| T0 workspaces + RLS | **PASS** | Migrations 096+ on `core`; RLS harness 59/59 (`rls_isolation_proof.log`, 2026-08-30 15:24). |
| K1 Alpaca paper adapter | **PASS (code)** | Merged; runtime paper connect **BLOCKED** (no Alpaca OAuth/keys; Turnstile wall — not re-burned). |
| K2 IBKR read-first | **PASS (code)** | Merged; vendor onboarding **BLOCKED** (human). |
| T1 Supabase Auth login | **PASS (code)** | Merged; Google+GitHub providers on `core` **BLOCKED** (human). |
| K3 credential vault | **PASS (code)** | Merged; master key in VM **SET**; project EF secrets **BLOCKED** (no `sbp_`). |
| T2 Stripe tiers | **PASS (code)** | EFs ACTIVE; Stripe test products/keys/webhook **BLOCKED** (hCaptcha — not re-burned). |
| T5 tier-gated UI | **PASS** | Vitest refresh: 42 passed (`olympus-tier-gates-refresh.log`). |
| K4 order-intent router + mirror | **PASS** | Kairos unit 67 passed (`kairos-router-unit-refresh.log`); live venue gates 8 passed. |
| T3 Settings UI + EF | **PASS (code + EF)** | settings **v11** + smoke 401; vault seal at runtime needs EF secrets. |
| K5 digest email | **PASS (code)** | Notify unit previously green; Mailgun send **BLOCKED** (empty API key / domain). |
| T4 overlay pipeline | **PASS (code)** | Overlay unit covered in prior chain regression; entitled chain integration 2/2 this turn. |

---

## Program-level acceptance (EPIC.md)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| House pipeline regression (`pytest -m unit tests/dq/olympus/`) | **PASS** | `house-olympus-unit.log` — 420 passed (2026-08-30 15:22). |
| RLS proof (user A ↛ B; anon zero private) | **PASS** | `rls_isolation_proof.log` — **59/59**, NOTICE `RLS proof PASSED` (includes 106 + staged 900). Cutover **900 not applied** to `core` (correct). |
| E2E staging: signup → Stripe → Alpaca → overlay → fill → digest | **BLOCKED** | Requires Stripe TEST + Alpaca paper + Mailgun + Auth providers. Not faked. |
| No live `submit_order` without flag + human path | **PASS** | `live-venue-gates-refresh.log` — 8 passed (`LiveVenueNotAuthorized`, stub raises, etc.). |

---

## Human-owned prerequisites (EPIC.md)

| Prerequisite | Status | Notes |
|--------------|--------|-------|
| Alpaca Connect OAuth app | **BLOCKED** | Signup Turnstile / Cognito; no usable keys. |
| IBKR OAuth 1.0a vendor email | **BLOCKED** | Human. |
| Stripe test products + webhook secret | **BLOCKED** | hCaptcha wall (do not re-burn). |
| Mailgun API key + sending domain | **BLOCKED** | MCP ready but account keys empty; reCAPTCHA signup wall (do not re-burn). |
| Supabase Auth Google + GitHub on `core` | **BLOCKED** | Human dashboard. |
| `DIGIQUANT_VAULT_MASTER_KEY` in **deploy** secrets | **BLOCKED** | Present in VM; not on EF secrets (no secrets MCP / no `sbp_`). |
| Legal investment-adviser read | **BLOCKED** | Human; pre-live-cutover only. |

---

## Agent-reachable acceptance evidence (refreshed)

| Proof | Result | Artifact |
|-------|--------|----------|
| Chain integration (overlay → paper fill → alert) | **2 passed** | `kairos-chain-integration-refresh.log` |
| Kairos router/sync unit | **67 passed** | `kairos-router-unit-refresh.log` |
| Live venue / submit_order gates | **8 passed** | `live-venue-gates-refresh.log` |
| Olympus tier gates (Vitest) | **42 passed** | `olympus-tier-gates-refresh.log` |
| Settings EF auth smoke | **401 / 401** | `settings-v11-smoke.log` |
| RLS isolation | **59/59 PASS** | `rls_isolation_proof.log` (+ summary extract) |
| House olympus unit | **420 passed** | `house-olympus-unit.log` (prior turn, same day) |

---

## Merges this turn

| PR | Result |
|----|--------|
| [#3179](https://github.com/digithings-ai/digithings/pull/3179) `cursor/kairos-cred-push-3d52` → `develop` | **MERGED** (`0f235935`) |

Prior on develop (unchanged): #3141 promotion, #3161 notifications, #3177 schema align, #3178 unlock status.

---

## Edge Functions (`core` / `rwagjbkvxkdwqmouagad`)

| Function | Version | Notes |
|----------|---------|-------|
| `settings` | **v11** | Thin GitHub-raw → `0f235935…/_shared/*`. Full 9-file bundle staged; CLI needs `sbp_`. |
| `stripe-webhook` | v3 | Awaits Stripe secrets |
| `create-checkout-session` | v1 | Awaits Stripe secrets |
| `customer-portal` | v3 | Awaits Stripe secrets |
| `prices-live` | v6 | Pre-existing |

---

## Top blockers (ordered)

1. **Supabase `sbp_` PAT** (or dashboard) — only path to push EF secrets (`DIGIQUANT_VAULT_*`, `APP_URL`, Stripe, Mailgun, Alpaca OAuth). MCP has **no** secrets tool; JWT → Management API **403**.
2. **Stripe TEST** keys/prices/webhook — blocked by hCaptcha (do not re-burn).
3. **Mailgun** API key + domain + `NOTIFY_FROM` — MCP ready, keys empty; signup reCAPTCHA wall.
4. **Alpaca** paper OAuth/API keys — Turnstile / Cognito wall.
5. **Auth providers** Google+GitHub on `core`.
6. **IBKR vendor** + **legal** (human; live-cutover gated).
7. **E2E staging paper chain** — depends on 1–5; not agent-fakeable.
8. **Pages promote** `develop`→`main` — human release-gate (auth flag off; cutover 900 inert).

---

## Remaining objective items (for TodoWrite / parent)

- [ ] Obtain `sbp_` PAT → push vault + APP_URL EF secrets → optional full 9-file settings redeploy
- [ ] Human: Stripe TEST + Mailgun + Auth providers + Alpaca OAuth (outside captcha re-burn)
- [ ] Staging E2E paper chain once secrets land
- [ ] Human: IBKR vendor + legal before any live epic
- [ ] Human: pages promote when ready (no 900, auth flag off)
- [ ] **Do not** mark goal complete until E2E + human gates clear
