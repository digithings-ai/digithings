# Kairos epic — completion audit (fresh, 2026-08-30T19:10Z)

**Verdict: NOT COMPLETE** — do not UpdateGoal complete.

Agent run: fresh secrets scan + Agentmail Auth unlock + re-run agent-reachable suites + EPIC acceptance table.

---

## Goal complete?

**NO.** Staging E2E (signup → Stripe → Alpaca paper → overlay → fill → digest) remains **BLOCKED** on vendor secrets. Workspace bootstrap for new Auth users is a newly evidenced product gap (`WORKSPACE_FORBIDDEN`).

---

## Newly unlocked this turn

| Item | Evidence |
|------|----------|
| **Agent-owned Auth user** (`auth.users=1`, confirmed) via Agentmail email signup + confirm + password login — **not** invented SQL | `/opt/cursor/artifacts/settings-jwt-e2e-agentmail.log` |
| Real JWT against settings EF v18 | same log — profile/notifications/brokers → **403 WORKSPACE_FORBIDDEN** |
| Checkout with JWT reaches price check | `PRICE_NOT_CONFIGURED` (Stripe prices absent) |
| Fresh unit / paper-fakes suites | house 287, notify+tier 62, kairos 67, chain+adapters (see logs below) |

## Still blocked (names only)

- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_BASELINE_MONTHLY`, `STRIPE_PRICE_CUSTOM_MONTHLY`
- `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `NOTIFY_FROM` (Mailgun MCP auth fail)
- `AUTH_GOOGLE_CLIENT_ID` / `AUTH_GOOGLE_CLIENT_SECRET` (Google Auth Disabled)
- `ALPACA_OAUTH_CLIENT_ID` / `ALPACA_OAUTH_CLIENT_SECRET`
- Cursor env paste of `SUPABASE_ACCESS_TOKEN` (`sbp_…`) — process env **ABSENT**; file `.local/secrets/cursor-cloud-agent-supabase-pat` works when loaded manually
- **Workspace bootstrap** — no product path creates `workspace_members` for new Auth users (members=0; 2 orphan enterprise system/house workspaces)
- Cutover `900_drop_anon_read_cutover.sql` — human gate
- Draft PR **#3183** Pages promote — leave draft
- IBKR vendor onboarding + legal adviser read — out of epic live-trading gate

---

## EPIC.md acceptance — requirement-by-requirement

### Child work packages (12)

| WP | Status | Evidence |
|----|--------|----------|
| K0–K5, T0–T5 code | **PASS** (on `develop`) | Promotion #3141 + follow-ups; EPIC checkboxes marked |
| Settings EF | **PASS** | `settings` **v18 ACTIVE** (`list_edge_functions`) |
| Migrations 096–106 | **PASS** | Prior apply + stamps; cutover **900 NOT applied** |

### Program-level acceptance

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | House pipeline regression `pytest -m unit tests/dq/olympus/` | **PASS** | `/opt/cursor/artifacts/house-olympus-unit-fresh.log` — **287 passed** |
| 2 | RLS proof (pre-cutover) | **PASS** | `/opt/cursor/artifacts/agent-reachable-gates-summary.log` + `rls_isolation_proof.log` — **59/59** (prior turn ~18:56Z; still authoritative) |
| 3 | E2E staging: signup → Stripe → Alpaca → overlay → fill → digest | **BLOCKED** | Vendors empty; workspace bootstrap gap; no Mailgun send |
| 4 | No live `submit_order` without flag | **PASS** | Alpaca adapter unit pins (`test_live_env_raises`) in paper-fakes log |

### Human prerequisites (EPIC)

| Prerequisite | Status | Notes |
|--------------|--------|-------|
| Alpaca Connect OAuth app | **BLOCKED** | signup notes only; no OAuth client secrets |
| IBKR OAuth vendor email | **BLOCKED** | longest pole; out of paper path |
| Stripe test products + webhook | **BLOCKED** | no `sk_test` / `whsec` / `price_` |
| Mailgun API key + domain | **BLOCKED** | env empty; MCP `get-v4-domains` auth fail |
| Supabase Auth Google+GitHub | **PARTIAL** | GitHub Enabled; Google Disabled; **Email Enabled** (Agentmail path works) |
| `DIGIQUANT_VAULT_MASTER_KEY` in deploy | **PASS** | EF secret name present |
| Legal adviser read | **BLOCKED** | human; before live-cutover epic |

---

## Secrets scan (names / presence only — values never logged)

Source artifact: `/opt/cursor/artifacts/kairos-secrets-scan-fresh.json`

| Source | Nonempty of interest | Empty / absent |
|--------|----------------------|----------------|
| Process env | `DIGIQUANT_VAULT_*`, `AUTH_URL` | `SUPABASE_ACCESS_TOKEN`, all Stripe/Mailgun/Alpaca/Google |
| `.local/secrets/` | `sbp_` PAT (label **cursor cloud agent**), GitHub OAuth client id/secret, vault, APP_URL; signup-note files | No Stripe/Alpaca **API** keys |
| EF secrets (`core`) | 12 names: vault, APP_URL, platform SUPABASE_*, FINNHUB | All 11 vendor names still absent |
| GitHub Actions secrets | **403** via `gh` (cannot list) | Prior dashboard scan: no STRIPE/ALPACA/MAILGUN names |

Mailgun MCP: namespace `ready` but API **Authentication failed**. Agentmail MCP: org `digithings` + inboxes usable.

---

## Agent-reachable suites (this turn)

| Suite | Result | Log |
|-------|--------|-----|
| House olympus (excl. kairos/overlay) | 287 passed | `house-olympus-unit-fresh.log` |
| Notify + tier gates | 62 passed | `notify-tier-gates-fresh.log` |
| Kairos olympus | 67 passed | `kairos-olympus-unit-fresh.log` |
| Brokers+vault+overlay (prior ~18:58) | 317 passed | `kairos-unit-suites.log` |
| Paper E2E fakes (**NOT staging**) | chain 2 + alpaca 34 + contracts/venue 66 + kairos 67 + ibkr 36 | `kairos-e2e-paper-fakes-fresh.log` |
| Settings unauth | 401×3; webhook `STRIPE_NOT_CONFIGURED` | `settings-v18-smoke-fresh.log` |
| Settings **with** Agentmail JWT | 403 WORKSPACE_FORBIDDEN | `settings-jwt-e2e-agentmail.log` |

---

## Auth path detail (agent-owned)

1. `POST /auth/v1/signup` with `*@agentmail.to` → user created, confirmation sent.
2. Agentmail inbox created; resend confirmation; received **Confirm Your Signup** from Supabase Auth.
3. `GET /auth/v1/verify` → 303 with session; password grant → JWT.
4. `auth.users=1` confirmed; **did not** invent SQL users.
5. Settings requires `workspace_members` — **none exist** (0 members). No insert performed (product bootstrap missing).

---

## PRs / branches

| Item | Action |
|------|--------|
| Docs branch | `cursor/kairos-audit-agentmail-auth-3d52` |
| #3183 | **LEAVE DRAFT** — do not merge |
| Goal | **FAIL complete** |

### Compare URL

```text
https://github.com/digithings-ai/digithings/compare/develop...cursor/kairos-audit-agentmail-auth-3d52
```

---

## Exact next human actions

1. Paste into Cursor Cloud env: `SUPABASE_ACCESS_TOKEN` (`sbp_…` from `.local/secrets/cursor-cloud-agent-supabase-pat`, label **cursor cloud agent**) + all Stripe / Mailgun / Alpaca OAuth names listed above.
2. Stripe test mode: products Baseline+Custom, webhook → `…/functions/v1/stripe-webhook`, paste `sk_test` / `whsec` / `price_` ids.
3. Mailgun: valid API key + verified domain + `NOTIFY_FROM` (MCP currently fails auth).
4. Alpaca: finish paper OAuth app; paste client id/secret.
5. Product/ops: **workspace bootstrap** for Observer (free) on first Auth session — today settings returns `WORKSPACE_FORBIDDEN` for real JWTs with zero memberships.
6. Optional Google OAuth when captcha-free.
7. Only after staging E2E green: intentional Pages cutover (merge #3183 when ready) + flag + cutover SQL 900.


---

## Prior audit trail (historical)

# Kairos epic — completion audit (2026-08-30)

**Verdict: NOT COMPLETE** — do not UpdateGoal complete.

## Follow-up turn (workspace bootstrap — Agentmail JWT past WORKSPACE_FORBIDDEN)

Agent run: migration **107** `ensure_personal_workspace` + `auth.users` trigger + backfill applied on `core`; settings EF **v19** (`ensureCallerWorkspace`). Agentmail JWT probe → **200** profile/notifications/brokers; checkout **PRICE_NOT_CONFIGURED**. Branch `cursor/workspace-bootstrap-ensure-6434`. Vendors still empty. Leave [#3183](https://github.com/digithings-ai/digithings/pull/3183) draft; no UpdateGoal complete.

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Workspace bootstrap | **PASS** | mig 107 on core; members=1; free personal workspace |
| 2 | Settings JWT E2E | **PASS (Observer reads)** | `/opt/cursor/artifacts/settings-jwt-e2e-agentmail-post-v19.log` — 200/200/200 |
| 3 | settings EF v19 | **PASS** | ACTIVE version **19** |
| 4 | Checkout | **BLOCKED** | `PRICE_NOT_CONFIGURED` (Stripe prices empty) |
| 5 | Vendor secrets | **BLOCKED** | Stripe/Mailgun/Google/Alpaca still empty |
| 6 | #3183 / goal | **LEAVE DRAFT / FAIL complete** | No merge; no UpdateGoal complete |

### Compare (bootstrap)

```text
https://github.com/digithings-ai/digithings/compare/develop...cursor/workspace-bootstrap-ensure-6434
```

---

## Follow-up turn (post-sbp: merge docs PRs + secrets scan + smoke)

Agent run: rebase+merge [#3209](https://github.com/digithings-ai/digithings/pull/3209) + [#3211](https://github.com/digithings-ai/digithings/pull/3211) (CI green). Load `sbp_` from `.local/secrets/cursor-cloud-agent-supabase-pat` → 12 EF secret names. Confirm settings **v18** ACTIVE; Auth GitHub **Enabled** / Google **Disabled**. Scan GitHub org+repo Actions secrets (dashboard session) — **no** `STRIPE_*` / `ALPACA_*` / `MAILGUN_*` names. Mailgun env empty → skip EF set. Cursor env still missing pasted PAT/vendors (`request-environment-setup-actions` re-recorded). `auth.users` count **0** → no real JWT settings E2E (do not invent). Hatch bodies queued for parent (gh comment/label **403**). Leave [#3183](https://github.com/digithings-ai/digithings/pull/3183) draft; no UpdateGoal complete.

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Merge #3209 / #3211 | **PASS** | Rebased onto `develop`; Required CI green; merged 2026-08-30T18:49Z |
| 2 | Hatch comments+labels | **QUEUED for parent** | Bodies: `/opt/cursor/artifacts/kairos-reviews/pr-{3209,3211}-review.md`. `gh` → **403** |
| 3 | `sbp_` secrets list | **PASS** | Management API → 12 names; PAT label **cursor cloud agent**; prefix `sbp_` |
| 4 | Auth polish | **PASS (no further change)** | Dashboard: Email+GitHub Enabled; Google Disabled; site URL + redirects already set. Org quota banner noted (restricts 04 Sep 2026 if over quota) |
| 5 | GitHub secrets Stripe/Alpaca | **ABSENT** | Org: LLM keys only. Repo: Cloudflare/Supabase/project tokens. Env `production`: Cloudflare/D1. No vendor Kairos keys |
| 6 | Mailgun EF set | **SKIPPED** | `MAILGUN_API_KEY` empty; MCP auth fail |
| 7 | Cursor env paste | **STILL MISSING** | Process env has no `SUPABASE_ACCESS_TOKEN`/`sbp_`; vendors empty |
| 8 | Settings v18 smoke | **PASS (unauth)** | `/opt/cursor/artifacts/settings-v18-smoke.log` — profile/notifications/brokers 401; webhook `STRIPE_NOT_CONFIGURED` |
| 9 | Real JWT settings E2E | **BLOCKED** | `auth.users` = 0; 2 enterprise workspaces orphaned — do not invent test user |
| 10 | #3183 / goal | **LEAVE DRAFT / FAIL complete** | No merge; no UpdateGoal complete |

### Docs compare (this turn)

```text
https://github.com/digithings-ai/digithings/compare/develop...cursor/kairos-post-sbp-continue-f34a
```

---

## Prior follow-up (PAT recreate+revoke → **cursor cloud agent**)

Agent run: load rotated `sbp_` from `.local/secrets/cursor-cloud-agent-supabase-pat` (sibling revoked kairos-named token; new token labeled **cursor cloud agent**). Verify Management API / `supabase secrets list` (names only). Confirm EF vault + `APP_URL` still present; settings **v18** ACTIVE. `request-environment-setup-actions` for **re-paste** into Cursor env. Update WAITING + docs note on [#3209](https://github.com/digithings-ai/digithings/pull/3209). Leave [#3183](https://github.com/digithings-ai/digithings/pull/3183) draft; no UpdateGoal complete.

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | New `sbp_` works | **PASS** | `supabase secrets list --project-ref rwagjbkvxkdwqmouagad` → 12 names; prefix `sbp_` |
| 2 | EF secrets vault + APP_URL | **PASS** | Names present: `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL` |
| 3 | settings EF | **PASS** | **ACTIVE** version **18** |
| 4 | Cursor env re-paste | **REQUESTED** | `request-environment-setup-actions` — new PAT as **cursor cloud agent** (old paste invalid) |
| 5 | Stripe / Mailgun / Google / Alpaca | **BLOCKED** | Still missing; listed in WAITING blockers |
| 6 | Docs / WAITING | **PASS** | Rotation note (recreate+revoke, no values); artifact `/opt/cursor/artifacts/kairos-WAITING-ON-SECRETS.json` |
| 7 | #3183 / goal | **LEAVE DRAFT / FAIL complete** | No merge; no UpdateGoal complete |

## Prior follow-up (`sbp_` reconfirm + GitHub Auth + docs branch)

Agent run: reconfirm `sbp_` Management API secrets list; enable **GitHub** Auth on `core`; set site URL + Olympus redirect allow-list; skip Google/Mailgun/Stripe/Alpaca (captcha or empty). Docs on `cursor/cursor-cloud-agent-secrets-status-c8be`. Settings EF **v18** ACTIVE. Leave [#3183](https://github.com/digithings-ai/digithings/pull/3183) draft.

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `sbp_` still works | **PASS** | `GET /v1/projects/{core}/secrets` → 12 names; token prefix `sbp_` |
| 2 | Auth providers Google+GitHub | **PARTIAL** | GitHub **Enabled** (OAuth App `digiquant olympus` / id 3826274). Google **Disabled** (skipped captcha). Site URL `https://digiquant.io`; uri allow-list includes `/olympus/auth/callback/`. |
| 3 | Mailgun EF + smoke | **SKIPPED** | `MAILGUN_API_KEY` empty; MCP `get-v4-domains` auth fail |
| 4 | Stripe / Alpaca | **BLOCKED** | No API/OAuth keys; signup notes only; captcha walls |
| 5 | Docs / WAITING | **PASS** | EPIC / HUMAN-UNBLOCK / DEPLOYMENT / COMPLETION_AUDIT / `WAITING-ON-SECRETS.json` on secrets-status branch |
| 6 | `request-environment-setup-actions` | **PASS** | Remind paste PAT as **cursor cloud agent** + remaining Stripe/Mailgun/Alpaca/Google |
| 7 | #3183 / goal | **LEAVE DRAFT / FAIL complete** | No merge; no UpdateGoal complete |

### EF secret **names** on `core` (values never logged)

`APP_URL`, `DIGIQUANT_VAULT_KEY_ID`, `DIGIQUANT_VAULT_MASTER_KEY`, `FINNHUB_API_KEY`, `NEXT_PUBLIC_APP_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_DB_URL`, `SUPABASE_JWKS`, `SUPABASE_PUBLISHABLE_KEYS`, `SUPABASE_SECRET_KEYS`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL`

### Docs compare (parent if PR 403)

```text
https://github.com/digithings-ai/digithings/compare/develop...cursor/cursor-cloud-agent-secrets-status-c8be
```

---

## Prior audit trail (historical)

**Verdict: NOT COMPLETE** — do not UpdateGoal complete.

Agent run (this turn): secret rescan (no unlocks) + audit for settings **v14** / [#3196](https://github.com/digithings-ai/digithings/pull/3196) + refresh draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) tip to `origin/develop`.  
Develop tip at branch cut: `baa7766d` (#3198 digichat promote after #3196). Settings EF on `core`: **v14** ACTIVE (thin pin → `5b526914`). Still no `sbp_` / no new vendor secrets. No captcha.  
Human unblock (in-repo): [`HUMAN-UNBLOCK.md`](HUMAN-UNBLOCK.md). Artifact mirror: `/opt/cursor/artifacts/kairos-HUMAN-UNBLOCK.md`.

### Done-criteria % (this turn)

| Bucket | PASS | BLOCKED |
|--------|------|---------|
| Wave A–E WPs (12) | 12 code PASS | runtime vendor/secrets |
| Program acceptance (4) | 3 PASS | 1 BLOCKED (staging E2E) |
| Human prerequisites (7) | 0 | 7 BLOCKED |
| **Full epic Done** | ~**35–40%** | majority secrets/human |
| **Code/agent-reachable Done** | ~**85–90%** | staging E2E + deploy secrets; tier-gate fail-open **landed** (#3196 + EF v14) |

---

## Follow-up turn (settings v14 + #3196 land + #3183 tip sync)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Secret/env rescan (names only) | **PASS (no unlocks)** | No `sbp_`. JWT `SUPABASE_ACCESS_TOKEN` (`eyJ…`, len 1486). Mailgun/Stripe/Alpaca/Auth API keys empty/absent. Vault + `APP_URL` SET. Signup-note files only. **No** EF secrets push / Mailgun smoke. |
| 2 | Settings EF v14 after #3196 | **PASS (already live)** | Prior land agent: thin GitHub-raw pin → `5b526914…`; `list_edge_functions` → settings **version 14** ACTIVE. Smoke: `settings-v14-smoke.log` (401 across profile/notifications/brokers + bad JWT). |
| 3 | #3183 promote draft tip sync | **PASS (ff to develop tip)** | Branch was ancestor of develop with **0** unique commits; draft open. Force-with-lease `f92a8810`→`baa7766d` (= `origin/develop`). Still **draft**; **not** merged. |
| 4 | Non-secret code gap hunt | **NONE found** | Profile/Notify/Brokers tabs already hydrate; EF routes match `settings-api`. Client `tierFromSession` still JWT for **presentation** (fail-closed → free) — intentional; EF/RLS enforce `workspaces.plan_tier`. Stop after audit docs. |
| 5 | `request-environment-setup-actions` | **PASS** | Blocking secrets list re-recorded (sbp_/Stripe/Mailgun/Auth/Alpaca). |
| 6 | Goal complete? | **FAIL** | Same human/vendor blockers; do not UpdateGoal complete. |

### Nonempty secret **names** this re-scan (values never logged)

| Source | Nonempty names | Empty / absent of interest |
|--------|----------------|----------------------------|
| Process env | `SUPABASE_ACCESS_TOKEN` (JWT), `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL`, `AUTH_URL` | `MAILGUN_*`, `NOTIFY_FROM`; no Stripe/Alpaca/Auth API keys; **no** `sbp_` |
| `.env` / `.local/secrets/kairos.env` | `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL` | Mailgun empty |
| Signup notes only | `ALPACA_SIGNUP_*`, `STRIPE_SIGNUP_*` | Not vendor API keys |

### Docs compare (parent if PR 403)

```text
https://github.com/digithings-ai/digithings/compare/develop...cursor/kairos-audit-v14-3d52
```

---

## Prior follow-up (settings tier workspace gate + HUMAN-UNBLOCK in-repo)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Secret/env rescan (names only) | **PASS (no unlocks)** | No `sbp_`. JWT `SUPABASE_ACCESS_TOKEN` (`eyJ…`, len 1486). Mailgun/Stripe/Alpaca/Auth API keys empty/absent. Vault + `APP_URL` SET. Signup-note files only. **No** EF secrets push / Mailgun smoke. |
| 2 | Highest-value code gap | **BRANCH READY** | Settings entitlement preferred stale JWT `plan_tier` over `workspaces.plan_tier` (fail-open after cancel) — port of draft #3149 onto `cursor/settings-tier-workspace-gate-3d52`. Deno settings suite green. |
| 3 | Wire HUMAN-UNBLOCK into DEPLOYMENT | **PASS** | In-repo `HUMAN-UNBLOCK.md`; linked from `DEPLOYMENT.md` header + §5. |
| 4 | `request-environment-setup-actions` | **PASS** | Blocking secrets list re-recorded (sbp_/Stripe/Mailgun/Auth/Alpaca). |
| 5 | #3183 promote draft | **LEAVE DRAFT** | Not merged. |
| 6 | Goal complete? | **FAIL** | Same human/vendor blockers; do not UpdateGoal complete. |

### Nonempty secret **names** this re-scan (values never logged)

| Source | Nonempty names | Empty / absent of interest |
|--------|----------------|----------------------------|
| Process env | `SUPABASE_ACCESS_TOKEN` (JWT), `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL`, `AUTH_URL` | `MAILGUN_*`, `NOTIFY_FROM`; no Stripe/Alpaca/Auth API keys; **no** `sbp_` |
| `.env` / `.local/secrets/kairos.env` | `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL` | Mailgun empty |
| Signup notes only | `ALPACA_SIGNUP_*`, `STRIPE_SIGNUP_*` | Not vendor API keys |

### Tier-gate compare (parent)

```text
https://github.com/digithings-ai/digithings/compare/develop...cursor/settings-tier-workspace-gate-3d52
```

Supersedes draft [#3149](https://github.com/digithings-ai/digithings/pull/3149) (same fix, rebased on current `develop`). Parent may close #3149 after opening/merging this branch.

---

## Prior follow-up (human-unblock + merge #3191)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Merge #3191 when CI green | **PASS** | Marked ready; Required CI + CodeQL green; `gh pr merge --merge` → `c751949c` (2026-08-30T17:21:20Z). |
| 2 | Hatch #3191 | **QUEUED for parent** | Body: `/opt/cursor/artifacts/kairos-reviews/pr-3191-review.md`. `gh` comment + `reviewed:agent` → **403**. |
| 3 | Secret/env rescan (names only) | **PASS (no unlocks)** | No `sbp_`. JWT `SUPABASE_ACCESS_TOKEN` (`eyJ…`, len 1486). Mailgun/Stripe/Alpaca/Auth API keys empty/absent. Vault + `APP_URL` SET. Signup-note files only. **No** EF secrets push. |
| 4 | `request-environment-setup-actions` | **PASS** | Single blocking list recorded (sbp_ PAT, Stripe sk_test + prices + whsec, Mailgun key+domain+from, Auth Google/GitHub client secrets, Alpaca OAuth). `get-message-queue` unavailable (legacy workflow). |
| 5 | `kairos-HUMAN-UNBLOCK.md` | **PASS** | `/opt/cursor/artifacts/kairos-HUMAN-UNBLOCK.md` — ordered checklist after secrets land. |
| 6 | #3183 promote draft | **LEAVE DRAFT** | Not merged. |
| 7 | Goal complete? | **FAIL** | Same human/vendor blockers; do not UpdateGoal complete. |

### Nonempty secret **names** this re-scan (values never logged)

| Source | Nonempty names | Empty / absent of interest |
|--------|----------------|----------------------------|
| Process env | `SUPABASE_ACCESS_TOKEN` (JWT), `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL`, `AUTH_URL` | `MAILGUN_*`, `NOTIFY_FROM`; no Stripe/Alpaca/Auth API keys; **no** `sbp_` |
| `.env` / `.local/secrets/kairos.env` | `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL` | Mailgun empty |
| Signup notes only | `ALPACA_SIGNUP_*`, `STRIPE_SIGNUP_*` | Not vendor API keys |

---

## Prior follow-up (wins hunt: secrets + brokers + vault + billing)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Secret/env rescan (names only) | **PASS (no unlocks)** | No `sbp_`. JWT `SUPABASE_ACCESS_TOKEN`. Mailgun/Stripe/Alpaca API keys empty/absent. Vault + `APP_URL` SET. `~/.supabase` telemetry only. **No** EF secrets push / Mailgun smoke. |
| 2 | Brokers tab hydrate gap | **PASS (already on develop)** | `BrokersTab` `useEffect` → `listBrokers` → GET `/settings/brokers`; EF handler present. Unauth 401/401 (`settings-brokers-get-smoke.log`). **No PR** — not notify/profile-class bug. |
| 3 | Local vault path (VM env key) | **PASS** | `kairos-vault-env-evidence.log` — `load_master_key(os.environ)` seal/open + `key=None`; vault **76** + connections **41**. Not EF secrets. |
| 4 | Billing EF smoke (no Stripe keys) | **PASS (honest)** | `billing-ef-smoke.log` — checkout/portal **401** (missing + invalid JWT); webhook **500 STRIPE_NOT_CONFIGURED**; prices-live **401**. |
| 5 | Merge #3188 | **PASS** | Merged → `a8eadc32`. |
| 6 | #3183 promote draft | **LEAVE DRAFT** | Not merged. |
| 7 | Goal complete? | **FAIL** | Same human/vendor blockers; do not UpdateGoal complete. |

### Nonempty secret **names** this re-scan (values never logged)

| Source | Nonempty names | Empty / absent of interest |
|--------|----------------|----------------------------|
| Process env | `SUPABASE_ACCESS_TOKEN` (JWT), `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL`, `AUTH_URL` | `MAILGUN_*`, `NOTIFY_FROM`; no Stripe/Alpaca API keys; **no** `sbp_` |
| `.env` / `.local/secrets/kairos.env` | `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL` | Mailgun empty |
| Signup notes only | `ALPACA_SIGNUP_*`, `STRIPE_SIGNUP_*` | Not vendor API keys |

### Brokers PR / compare

```text
N/A — hydrate already on develop (no cursor/brokers-tab-hydrate branch)
```

---

## Prior follow-up (post-#3187: profile GET + EF v13 + audit)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Hatch + merge #3187 | **PASS (merge; hatch 403)** | `gh pr comment` / `reviewed:agent` → **403**. Marked ready; Required CI green; `gh pr merge --merge` → `17a84b30` (2026-08-30T16:59:04Z). Parent can hatch. |
| 2 | Redeploy settings EF thin-pin to merge SHA | **PASS** | MCP `deploy_edge_function` → **v13** ACTIVE; pin `17a84b3042d6…` (GET `/profile` + GET `/notifications` handlers). |
| 3 | Smoke 401 (profile + notifications) | **PASS** | Missing + invalid JWT → gateway `401` (`settings-v13-smoke.log`). |
| 4 | Secret scan (nonempty names only) | **PASS (no unlocks)** | No `sbp_`. `SUPABASE_ACCESS_TOKEN` still JWT. Mailgun/Stripe/Alpaca API keys empty/absent. Signup-note files only. Vault + `APP_URL` SET. **No** EF secrets push / Mailgun smoke. |
| 5 | Merge #3188 (this audit) | **PASS** | Merged as `a8eadc32` (2026-08-30). |
| 6 | #3183 promote draft | **LEAVE DRAFT** | Not merged. |
| 7 | Goal complete? | **FAIL** | Same human/vendor blockers; do not UpdateGoal complete. |

### Nonempty secret **names** this re-scan (values never logged)

| Source | Nonempty names | Empty / absent of interest |
|--------|----------------|----------------------------|
| Process env | `SUPABASE_ACCESS_TOKEN` (JWT), `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL`, `AUTH_URL` | `MAILGUN_*`, `NOTIFY_FROM`; no Stripe/Alpaca API keys; **no** `sbp_` |
| `.env` / `.local/secrets/kairos.env` | `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL` | Mailgun empty |
| Signup notes only | `ALPACA_SIGNUP_*`, `STRIPE_SIGNUP_*` | Not vendor API keys |

---

## Follow-up turn (post-#3186: merge + secret rescan + reviews + profile GET)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Merge #3186 when CI green | **PASS** | Marked ready; Required CI + CodeQL green; `gh pr merge --squash` → `b9e1e8e3` (2026-08-30T16:47:09Z). |
| 2 | Secret scan (nonempty names only) | **PASS (no unlocks)** | No `sbp_`. `SUPABASE_ACCESS_TOKEN` still JWT. Mailgun/Stripe/Alpaca API keys empty/absent. Vault + `APP_URL` SET. **No** EF push / redeploy / Mailgun smoke. |
| 3 | In-session review markdown | **QUEUED for parent** | Bodies under `/opt/cursor/artifacts/kairos-reviews/pr-{3141,3177–3181,3186}-review.md`. `gh` comment + `reviewed:agent` → **403**. #3161 + #3184 + #3185 already hatched on GitHub. |
| 4 | Non-secret code gap | **BRANCH READY** | Missing GET `/profile` (ProfileTab blank defaults) → `cursor/profile-get-hydrate-539c` @ `140bf203`. Deno 32 + Vitest 13 green. `gh pr create` → **403** — parent opens from compare URL. |
| 5 | #3183 promote draft | **LEAVE DRAFT** | Not merged. |
| 6 | Goal complete? | **FAIL** | Same human/vendor blockers; do not UpdateGoal complete. |

### Nonempty secret **names** this re-scan (values never logged)

| Source | Nonempty names | Empty / absent of interest |
|--------|----------------|----------------------------|
| Process env | `SUPABASE_ACCESS_TOKEN` (JWT), `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL`, `AUTH_URL` | `MAILGUN_*`, `NOTIFY_FROM`; no Stripe/Alpaca API keys; **no** `sbp_` |
| `.env` / `.local/secrets/kairos.env` | `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL` | Mailgun empty |
| Signup notes only | `ALPACA_SIGNUP_*`, `STRIPE_SIGNUP_*` | Not vendor API keys |

### Profile GET compare (parent)

```text
https://github.com/digithings-ai/digithings/compare/develop...cursor/profile-get-hydrate-539c
```

---

## Follow-up turn (post-#3185: merge + secret rescan + paper E2E fakes)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Merge #3185 when CI green | **PASS** | Marked ready; Required CI + CodeQL green; `gh pr merge --merge` → `ae11f0d3` (2026-08-30T16:41:10Z). |
| 2 | Secret scan (nonempty names only) | **PASS (no unlocks)** | No `sbp_`. `SUPABASE_ACCESS_TOKEN` still JWT (`eyJ…`, len 1486). `MAILGUN_*` / `NOTIFY_FROM` empty. No Stripe/Alpaca **API** keys (signup-note files only). Vault + `APP_URL` SET in VM. **No** EF secrets push / settings redeploy / Mailgun smoke. |
| 3 | Settings EF still v12 | **PASS** | `list_edge_functions` → `settings` version **12** ACTIVE. Smoke: `settings-v12-smoke.log` (401/401). |
| 4 | E2E without live vendors (fakes/mocks) | **PASS (NOT live staging)** | Chain 2 + Alpaca 34 + contracts/venue 6 + kairos 67 + IBKR 36 — see `kairos-e2e-paper-fakes-refresh.log`. Explicitly **not** staging signup→Stripe→Alpaca→digest. |
| 5 | Review hatches for parent (#3184 / #3185) | **PARTIAL** | #3184: `reviewed:agent` + `<!-- in-session-review -->` comment **present**. #3185: later hatched on GitHub (reconfirmed this turn). |
| 6 | #3183 promote draft | **LEAVE DRAFT** | Not merged (human release-gate). |
| 7 | Goal complete? | **FAIL** | Same human/vendor blockers; do not UpdateGoal complete. |

### Nonempty secret **names** this re-scan (values never logged)

| Source | Nonempty names | Empty / absent of interest |
|--------|----------------|----------------------------|
| Process env | `SUPABASE_ACCESS_TOKEN` (JWT), `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL`, `AUTH_URL` | `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `NOTIFY_FROM`; no Stripe/Alpaca API keys; **no** `sbp_` |
| `.env` / `.local/secrets/kairos.env` | `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL` | Mailgun empty |
| Signup notes only | `ALPACA_SIGNUP_*`, `STRIPE_SIGNUP_*` | Not vendor API keys |

---

## Prior follow-up (post-#3181: merge + secret rescan + review/promote)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Merge #3181 when CI green | **PASS** | Marked ready; Required CI + CodeQL green; `gh pr merge --merge` → `f92a8810` (2026-08-30T16:20:08Z). |
| 2 | Secret scan (nonempty names only) | **PASS (no unlocks)** | No `sbp_`. `SUPABASE_ACCESS_TOKEN` still JWT (`eyJ…`, len 1486). Mailgun/Stripe/Alpaca/Auth provider keys **missing or empty**. Vault + `APP_URL` still SET in VM (unchanged). **No** EF secrets push / settings redeploy / Mailgun smoke. |
| 3 | Review hatches (`<!-- in-session-review -->` + `reviewed:agent`) | **BLOCKED (token)** | Diffs reviewed for #3147, #3148, #3156, #3161, #3177–#3181. Bodies written to `/opt/cursor/artifacts/kairos-reviews/pr-*-review.md`. `gh`/`api` comment + label → **403** Resource not accessible by integration. **Do not fake Bugbot.** Parent must post comments + labels with a write token. |
| 4 | Pages promote prep (flag off, no 900) | **BRANCH READY / PR BLOCKED** | Pushed `cursor/promote-kairos-pages-3d52` (= develop tip, ~199 ahead of main). `gh pr create --draft` → **403**. Recipe below. Cutover 900 **not** applied. |
| 5 | `request-environment-setup-actions` | **PASS** | Minimal blocking set recorded: `SUPABASE_ACCESS_TOKEN` (`sbp_`), Mailgun nonempty, Stripe TEST keys+prices+webhook, Auth provider client IDs, Alpaca paper OAuth. |
| 6 | Goal complete? | **FAIL** | Same human/vendor blockers; do not UpdateGoal complete. |

### Draft promote PR recipe (parent)

```text
base: main
head: cursor/promote-kairos-pages-3d52
draft: true
title: chore(promote): develop → main — Kairos Pages prep (flag-off, no cutover 900)
```

Body must require: Pages `NEXT_PUBLIC_OLYMPUS_AUTH` unset; do not apply `cutover/900`; Access stays on; merge only as deliberate release (~199 commits).

### Material review note (historical — fixed by #3184)

`NotifyTab` previously lacked GET/hydrate; **fixed** in #3184. Analogous ProfileTab gap addressed on `cursor/profile-get-hydrate-539c` (awaiting parent PR).

---

## Prior follow-up (merge #3180 + unlock hunt)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Merge #3180 if CI green | **PASS** | Marked ready; Required CI + CodeQL green; `gh pr merge --merge` → `bf34c015` (2026-08-30T16:14:52Z). |
| 2 | Re-scan env / `.env` / `.local/secrets` for **new nonempty** secrets | **PASS (no unlocks)** | Names + nonempty only. **No** value prefix `sbp_`. `SUPABASE_ACCESS_TOKEN` still JWT (`eyJ…`). `MAILGUN_*` / `NOTIFY_FROM` still **empty**. No `STRIPE_*` / `ALPACA_*` API keys (signup-note files only). Vault + `APP_URL` still SET in VM (unchanged). |
| 3 | Push EF secrets + full settings bundle if `sbp_` appeared | **SKIPPED** | No `sbp_` → no Management API / CLI secrets push; settings remains **v11** thin pin. |
| 4 | cursor-cloud `environment-info` / `get-message-queue` / setup-actions | **PASS** | Env linked (`ea5347f2-…`); `get-message-queue` → legacy workflow unsupported; events empty. Setup-action list **unchanged** → **no** `request-environment-setup-actions`. |
| 5 | Mailgun smoke to Agent Mail if keys nonempty | **SKIPPED** | Keys still empty; no send. Captcha signup **not** re-attempted. |
| 6 | Review gate (`reviewed:agent`) for later main | **DOCUMENTED** | See § Review gate. Labels **not** applied (CODE_REVIEW_POLICY requires `<!-- in-session-review -->` findings comment; this turn did not run fresh-context `/review`). |
| 7 | Goal complete? | **FAIL** | Same blockers; do not UpdateGoal complete. |

### Nonempty secret **names** this re-scan (values never logged)

| Source | Nonempty names | Empty / absent of interest |
|--------|----------------|----------------------------|
| Process env | `SUPABASE_ACCESS_TOKEN` (JWT), `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL`, `AUTH_URL` | `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `NOTIFY_FROM`; no `STRIPE_*` / `ALPACA_*` API keys; **no** `sbp_` |
| `.env` / `.local/secrets/kairos.env` | `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL` (+ LLM keys in `.env` unrelated to Kairos E2E) | Mailgun empty |
| Signup notes only | `ALPACA_SIGNUP_*`, `STRIPE_SIGNUP_*` | Not vendor API keys |

---

## Prior-turn objective checklist (cred-push / audit write)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Inspect develop vs #3179; merge if CI green | **PASS** | PR [#3179](https://github.com/digithings-ai/digithings/pull/3179) marked ready + merged (`0f235935`, 2026-08-30T16:00:32Z). Required CI + CodeQL green before merge. |
| 2a | Supabase MCP: secrets/env tools? | **FAIL / absent** | Full `GetDynamicTools(Supabase)` catalog: **no** secrets/env tools (only migrate/SQL/EF/branch/project). Cross-namespace search: no Supabase secrets tool. Reconfirmed this follow-up. |
| 2b | Push `DIGIQUANT_VAULT_*`, `APP_URL`/`NEXT_PUBLIC_APP_URL` to project EF secrets | **BLOCKED** | Values **present** in VM env / `.local/secrets` (names only; not logged). Management API `GET /v1/projects/…/secrets` → **403** (JWT `eyJ…`, not `sbp_`). CLI deploy also rejects non-`sbp_` token. |
| 2c | Redeploy full settings monorepo bundle; smoke 401 | **PASS (thin fallback)** | Full 9-file payload prepared (`/opt/cursor/artifacts/settings-deploy-final.json`, content hash `2fc5f9bb62727c7c`). MCP `deploy_edge_function` **thin** pin to post-#3179 tip → settings **v11**. Smoke: `settings-v11-smoke.log` — GET no-auth **401**, POST invalid JWT **401**. Direct Management API / raw MCP HTTP blocked (403). |
| 3 | Mailgun MCP `mcp_auth` if `needsAuth` | **PASS (skip)** | `namespaceStatus: ready` — no auth attempt (per instructions). Captcha/signup walls not re-burned. |
| 4 | Completion audit + EPIC delivery update | **PASS** | This file + `docs/agent-backlog/kairos-tenancy/EPIC.md` delivery section. |
| 5 | Re-run stale agent-reachable proofs | **PASS** | Chain / tier / live-venue refreshed prior turn. E2E paper **not** faked. |
| 6 | Branch `cursor/*-3d52`, push docs | **PASS** | `cursor/kairos-completion-audit-3d52` merged as #3180. |
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
| K3 credential vault | **PASS (code + VM env)** | Merged; local env seal/open **PASS** (`kairos-vault-env-evidence.log`); project EF secrets **BLOCKED** (no `sbp_`). |
| T2 Stripe tiers | **PASS (code)** | EFs ACTIVE; Stripe test products/keys/webhook **BLOCKED** (hCaptcha — not re-burned). |
| T5 tier-gated UI | **PASS** | Vitest refresh: 42 passed (`olympus-tier-gates-refresh.log`). |
| K4 order-intent router + mirror | **PASS** | Kairos unit 67 passed (`kairos-router-unit-refresh.log`); live venue gates 8 passed. |
| T3 Settings UI + EF | **PASS (code + EF)** | settings **v14** + smoke 401; vault seal at runtime needs EF secrets. Tier gate uses `workspaces.plan_tier` only (#3196). |
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

**Label: NOT live staging** — local fakes/mocks only (PostgREST/Mailgun/broker HTTP boundaries). Does **not** satisfy EPIC program E2E (signup → Stripe → Alpaca → overlay → fill → digest).

| Proof | Result | Artifact |
|-------|--------|----------|
| Combined paper-path E2E (fakes) | **145 passed** (2+34+6+67+36) | `kairos-e2e-paper-fakes-refresh.log` |
| Chain integration (overlay → paper fill → alert) | **2 passed** | (in combined log; also prior `kairos-chain-integration-refresh.log`) |
| Alpaca paper adapter (HTTP mocked) | **34 passed** | (in combined log) |
| Broker contracts / live venue members | **6 passed** | (in combined log; prior live-venue suite also green) |
| Kairos router/sync unit | **67 passed** | (in combined log) |
| IBKR adapter unit | **36 passed** | (in combined log) |
| Olympus tier gates (Vitest) | **42 passed** | `olympus-tier-gates-refresh.log` (prior same day) |
| Settings EF auth smoke | **401 / 401** | `settings-v14-smoke.log` (+ prior brokers GET: `settings-brokers-get-smoke.log`) |
| Local env vault seal/open | **PASS** | `kairos-vault-env-evidence.log` (76 vault + 41 connections) |
| Billing EF unauth / not-configured | **PASS (honest)** | `billing-ef-smoke.log` — 401 / `STRIPE_NOT_CONFIGURED` |
| RLS isolation | **59/59 PASS** | `rls_isolation_proof.log` (+ summary extract) |
| House olympus unit | **420 passed** | `house-olympus-unit.log` (prior turn, same day) |

---

## Merges

| PR | Result |
|----|--------|
| [#3196](https://github.com/digithings-ai/digithings/pull/3196) `cursor/settings-tier-workspace-gate-3d52` → `develop` | **MERGED** (`5b526914`) — settings EF **v14** |
| [#3193](https://github.com/digithings-ai/digithings/pull/3193) human-unblock checklist sync | **MERGED** (`a8ba8d3a`) |
| [#3191](https://github.com/digithings-ai/digithings/pull/3191) `cursor/kairos-wins-audit-d905` → `develop` | **MERGED** (`c751949c`) |
| [#3188](https://github.com/digithings-ai/digithings/pull/3188) `cursor/kairos-audit-v13-539c` → `develop` | **MERGED** (`a8eadc32`) |
| [#3187](https://github.com/digithings-ai/digithings/pull/3187) `cursor/profile-get-hydrate-539c` → `develop` | **MERGED** (`17a84b30`) |
| [#3186](https://github.com/digithings-ai/digithings/pull/3186) `cursor/kairos-audit-v12-3d52` → `develop` | **MERGED** (`b9e1e8e3`) |
| [#3185](https://github.com/digithings-ai/digithings/pull/3185) `cursor/settings-hydrate-land-5e7e` → `develop` | **MERGED** (`ae11f0d3`) |
| [#3184](https://github.com/digithings-ai/digithings/pull/3184) `cursor/settings-notify-hydrate-3d52` → `develop` | **MERGED** (`732a77d0`) |
| [#3181](https://github.com/digithings-ai/digithings/pull/3181) ops/status docs → `develop` | **MERGED** (`f92a8810`) |
| [#3179](https://github.com/digithings-ai/digithings/pull/3179) `cursor/kairos-cred-push-3d52` → `develop` | **MERGED** (`0f235935`) |
| [#3180](https://github.com/digithings-ai/digithings/pull/3180) `cursor/kairos-completion-audit-3d52` → `develop` | **MERGED** (`bf34c015`) |

Prior on develop (unchanged): #3141 promotion, #3161 notifications, #3177 schema align, #3178 unlock status.

**Not merged:** [#3183](https://github.com/digithings-ai/digithings/pull/3183) pages promote draft — tip synced to `baa7766d` (= `origin/develop`); leave draft until secrets live **and** intentional Pages cutover.
**Landed:** #3196 settings tier workspace gate (supersedes draft #3149).

---

## Review gate (for later `main` promotion)

`ci-review-coverage.yml` requires each non-bot commit reaching `main` to clear a review hatch (`reviewed:agent` + findings comment, Bugbot success, APPROVED, `reviewed:owner`, or `risk:low`). See [`docs/agents/CODE_REVIEW_POLICY.md`](../../agents/CODE_REVIEW_POLICY.md).

| Merged → `develop` (Kairos-adjacent) | `reviewed:agent` / hatch? | Note |
|--------------------------------------|---------------------------|------|
| #3120 T3 Settings, #3099 T1, #3119 T5, #3125 RLS, #3121 cutover docs | **yes** | OK for later main |
| #3141 digiquant promote | **no** | Review body queued: `pr-3141-review.md` |
| #3161 notifications wire | **yes** | Hatched on GitHub |
| #3177–#3181 docs/audit series | **no** | Bodies queued under `kairos-reviews/` |
| #3184 NotifyTab hydrate | **yes** | `reviewed:agent` + in-session-review comment |
| #3185 settings hydrate land note | **yes** | Hatched on GitHub (reconfirmed) |
| #3186 audit v12 refresh | **no** | Body queued: `pr-3186-review.md` |
| #3187 profile GET hydrate | **no** | Hatch 403 this agent — parent posts findings + `reviewed:agent` |
| #3188 audit v13 | **no** | Hatch 403 this agent — parent posts findings + `reviewed:agent` |
| #3191 wins-hunt audit | **no** | Hatch 403 this agent — body queued: `pr-3191-review.md` |
| #3196 settings tier workspace gate | **no** | Hatch 403 this agent — body queued: `pr-3196-review.md` |
| #3156 WP delivery docs | `needs-human-review` only | Not a coverage hatch |

**Parent-only:** post queued `<!-- in-session-review -->` comments + `reviewed:agent` (token 403 for this agent). Do **not** fake Bugbot. Leave #3183 draft.

Open develop drafts (coverage/bugfix, etc.) similarly lack hatches; not blocking Kairos code path until merge.

---

## Edge Functions (`core` / `rwagjbkvxkdwqmouagad`)

| Function | Version | Notes |
|----------|---------|-------|
| `settings` | **v14** | Thin GitHub-raw pin → `5b526914` (#3196 workspace `plan_tier` gate + #3187 GET `/profile` + #3184 GET `/notifications`). Full 9-file bundle staged; CLI/secrets need `sbp_`. Smoke: `settings-v14-smoke.log`. |
| `stripe-webhook` | v3 | Awaits Stripe secrets |
| `create-checkout-session` | v1 | Unauth smoke **401**; awaits Stripe secrets |
| `customer-portal` | v3 | Unauth smoke **401**; awaits Stripe secrets |
| `prices-live` | v6 | Unauth smoke **401** |

---

## Top blockers (ordered)

1. **Supabase `sbp_` PAT** (or dashboard) — only path to push EF secrets (`DIGIQUANT_VAULT_*`, `APP_URL`, Stripe, Mailgun, Alpaca OAuth). MCP has **no** secrets tool; JWT → Management API **403**.
2. **Stripe TEST** keys/prices/webhook — blocked by hCaptcha (do not re-burn).
3. **Mailgun** API key + domain + `NOTIFY_FROM` — MCP ready, keys empty; signup reCAPTCHA wall.
4. **Alpaca** paper OAuth/API keys — Turnstile / Cognito wall.
5. **Auth providers** Google+GitHub on `core`.
6. **IBKR vendor** + **legal** (human; live-cutover gated).
7. **E2E staging paper chain** — depends on 1–5; not agent-fakeable.
8. **Review hatches** on unhatched develop merges before `main` promote (#3141, #3161, #3177–#3181, #3185, …). #3184 already hatched.
9. **Pages promote** `develop`→`main` — human release-gate (auth flag off; cutover 900 inert); leave #3183 draft.

---

## Remaining objective items (for TodoWrite / parent)

- [ ] Obtain `sbp_` PAT → push vault + APP_URL EF secrets → optional full 9-file settings redeploy
- [ ] Human: Stripe TEST + Mailgun + Auth providers + Alpaca OAuth (outside captcha re-burn)
- [ ] Staging E2E paper chain once secrets land (local fakes E2E + local vault env already green — not substitutes)
- [ ] Fresh-context `/review` (or Bugbot / `reviewed:owner`) on unhatched Kairos merges before main
- [ ] Human: IBKR vendor + legal before any live epic
- [ ] Human: pages promote when ready (no 900, auth flag off); leave #3183 draft
- [x] Land `cursor/settings-tier-workspace-gate-3d52` / #3196 (workspace-only tier gate; supersedes #3149); settings EF **v14**
- [x] Refresh #3183 promote tip to current `origin/develop` (still draft; do not merge)
- [x] Brokers tab hydrate — already on develop (verified this turn; no PR)
- [x] Local VM vault seal/open evidence — `kairos-vault-env-evidence.log`
- [x] Billing EF unauth/not-configured smoke — `billing-ef-smoke.log`
- [x] HUMAN-UNBLOCK in-repo + linked from DEPLOYMENT.md
- [ ] **Do not** mark goal complete until staging E2E + human gates clear
