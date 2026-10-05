# Credential Ownership & Refresh Paths

> **Rule** (per `client-incidents.md` §9): *Any credential we hold by hand needs one owner, one refresh path, and a check that fails loudly when it is stale.*

This document registers every hand-held credential in the digithings monorepo with its **owner**, **canonical store**, **refresh path**, and **staleness detector**. No credential should exist in more than one canonical store.

---

## Never paste a credential value

**A credential value is never pasted into a ticket, an issue, a comment, an interaction
reason, or any chat surface — including by the credential owner, and including to help an
agent diagnose.** No one is exempt. Helping an agent is not a reason.

This is broader than "no secret values in docs" below. A doc is a file someone chose to
publish; a chat surface is where credential problems get discussed at 23:00 by someone
trying to be helpful. **DIG-1226** (2026-10-05) is why: the account holder rejected an
agent's confirmation card and quoted the value inline in the reject reason, to explain why
a refresh had failed. The reason text is stored on the interaction record itself, which
Security cannot edit or delete — the Paperclip API has no route for it. One well-meant
sentence became permanent on a third-party host.

The value was non-working, so nothing was exposed. That was luck, not design.

### When a refresh or a check fails, report this

| Report this | Never report this |
|---|---|
| Which check failed: the shape check, the live vendor verify, or the secret write | The value, in whole or in any part |
| The status the vendor returned (e.g. `401`) | Its length, its character count, or a prefix |
| The script's exit code | A screenshot, a diff, or a pasted command line |
| Which step of the documented refresh path you were on | A re-paste "just in case" |

**Agents ask for the branch the tool took, never for the value.** The refresh scripts in
this stack already name their own branch on stdout, so the branch plus the exit code is
sufficient to diagnose every failure we have seen. If a script's error does not tell you
which branch it took, that is a bug in the script — file it, do not ask for the value.

Values move only by script (`bws`, `bw`, `wrangler secret put`, `gh secret set`, macOS
Keychain via `dt-keys`). A value that reaches a human's hands to be copied is a value that
will eventually be pasted. That is the whole reason to remove hand-held credentials, and it
is the argument for retiring the twelve-x desk-session handoff (DIG-1226, action 5).

Twelve-x's own rule for this credential path, with the per-script detail, is
[`PRIMEMARKET_DESK_API.md`](https://github.com/digithings-ai/twelve-x/blob/develop/docs/PRIMEMARKET_DESK_API.md)
§ *Interim: a human-supplied session*.

---

## GLOOMBERB_SESSION_COOKIE

**Used by**: `digifetch` session-gated tools (42 of 89 tools; see `docs/ops/gloomberb-session-cookie.md`)

| Field | Value |
|-------|-------|
| **Owner** | Platform team |
| **Canonical store** | GitHub Actions `cron` environment secret `GLOOMBERB_SESSION_COOKIE` |
| **Refresh path** | Manual: `gh secret set GLOOMBERB_SESSION_COOKIE --env cron --body "<cookie-value>"` (or via GitHub UI: Settings → Environments → cron → Secrets) |
| **Staleness detector** | `DIG-345` — `session_catchup.yml` pre-flight secret check (todo) |
| **Local `.env`** | Developer convenience ONLY — not a production credential store. Value sourced from canonical store when needed. |
| **Hosted MCP container** | Forwarded from same canonical store via Cloudflare Workers secret (wired in `apps/digithings-stack-cloudflare/src/index.ts`, `DigiQuantMcpContainer.envVars`) |

**History**: Prior to 2026-10-04, this credential lived in two independent copies (GitHub `cron` secret + local `.env`). The `cron` secret expired 2026-09-25 → 2026-10-02, causing 8 days of silent 401 failures in scheduled `pipeline-digiquant.yml` runs while local runs succeeded. A manual refresh on 2026-10-02 fixed both copies by accident. This document establishes the single-owner rule to prevent recurrence.

**Runbook entry**: When the `cron` secret expires, the next scheduled `pipeline-digiquant.yml` run (triggered by `digithings-cron` → `repository_dispatch: digiquant-baseline`) will fail fast with a clear 401/auth error. Platform on-call: refresh the secret per the refresh path above, then re-run the failed workflow.

**If the refresh fails**: read the cookie out of the browser, take it to the shell, and
`gh secret set` it. If that command errors, report *the command's error and its exit code*
— never the cookie, never a prefix of it. See
[Never paste a credential value](#never-paste-a-credential-value).

---

## DataTap Azure — digichat Container App identities and inline secrets

**Resource under review** (DIG-1293 sweep 2026-10-06, `az … show` / `list` / `show-tags` / `role definition list` only — no ARM write, no secret value read; DIG-1344 followed on the same date with `az containerapp secret list --show-values` to compute **fingerprints only** — still read-only, still no ARM write, and no value read by a human or an agent):

```
subscription  fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0   "DataTap WebSite"  (East US 2)
tenant        ac621ee5-844e-4fc9-b757-e3a3c77269b6   datatapstream.onmicrosoft.com
prod          datatap-rg / digichat        ACA, env datatap-cae
dev           datatap-dev-rg / digichat    ACA, env datatap-dev-cae
registry      datatapchatregistry.azurecr.io   (SKU Basic, RG datatap-rg)
```

This is **DataTap's** tenant, not ours, but the rule at the top of this file applies unchanged: anything digithings hands into that tenant needs one owner, one refresh path, and a check that fails loudly when it is stale.

Every `az` command in this section — including the refresh paths — is refused by [`scripts/az-guard/az`](../../scripts/az-guard/az) until a subscription is on the register. See [`datatap-azure-az-guard.md`](datatap-azure-az-guard.md).

One deliberate departure from the schema below: owners here are **named humans, not teams.** The usual rule is a team, but a client tenant has no digithings team to name, and "the owner" is only actionable when a person answers to it.

### Named human owner of the production write

| Field | Value |
|-------|-------|
| **Owner** | **Chris Stefan** — the digithings side of the production write. He is the `production` GitHub environment's required reviewer (`chrizefan`, read from `GET /repos/digithings-ai/digithings/environments/production`). He is also the operator on whose Mac the authenticated Azure session runs as the shared account (`az account show --query user` returns that UPN, `type: user`). |
| **Backup / DataTap side** | **Unassigned — this is the gap.** No individual user in the tenant holds any role assignment on the subscription. `az ad user list` returns five users (`DataTap`, `Info`, `Nick Stefan`, `Pierre Chamberland`, `Trials Registration`); the shared account's `memberOf` is empty. The only `Owner` of `fc64972f-…` is the **shared** account `datatap@datatapstream.onmicrosoft.com`, so it cannot be given least privilege without breaking whoever depends on it, and **who holds its credential is recorded nowhere.** |
| **Required change** | Name a DataTap-side human for the tenant `Owner` role, record who holds the shared account's credential, and move day-to-day work onto per-person accounts (PIM / break-glass). That is a DataTap-side decision; raise it with DataTap through Counsel's provider contact rather than acting on the shared account. |

### Principals and their role assignments

Nothing below holds a credential. Values were never read; these are object ids, display names and role definitions only.

| Principal | Type | Assignments (exact) | Credential state |
|-----------|------|---------------------|------------------|
| `datatap-digichat-deploy` — SP `44cfda92-c0d1-46ad-8fab-0e30c80c25d2`, app `be54468d-2f66-4aeb-a231-5db0b6e58789` | Service principal (Application) | `Contributor` on `datatap-rg/digichat` (2026-08-17) · `Contributor` on `datatap-dev-rg/digichat` (2026-08-09) · `Contributor` on ACR `datatapchatregistry` (2026-08-09) | **None.** `keyCredentials: []`, `passwordCredentials: []`, `federatedIdentityCredentials: null`. Dormant, not deleted (`deletedDateTime: null`). |
| `digichat` prod system-assigned identity `e56a35e6-7d5b-411c-8490-70605a4732b2` (appId `bc89d945-…`) | Managed identity | `AcrPull` on `datatapchatregistry` (2026-07-19) | Managed identity — no stored credential, token minted by ARM. |
| `digichat` dev system-assigned identity `e338abce-cf20-4113-b280-72a8e123b8a4` (appId `503aa808-…`) | Managed identity | `AcrPull` on `datatapchatregistry` (2026-07-19) | Managed identity — no stored credential. |
| `datatap-web-github-deploy` `3f597b0e-fedc-4078-86e4-7e41b21cf748` | Service principal | `Contributor` on the whole subscription (2026-07-15, inherited by every scope below) | None — `keyCredentials: []`, `passwordCredentials: []`. |
| `datatap-digichat-sync` `f2954085-c40f-4ea4-bd76-5ccf8b4dc57a` | Service principal | `Reader` on the whole subscription (2026-09-28, inherited) | None. |
| `datatap@datatapstream.onmicrosoft.com` `a26eb0a1-…` | **User (shared)** | `Owner` on the subscription (2026-07-15) | Interactive sign-in. Shared password + the auth factors on that account. |

### What `Contributor` actually grants — read this before trusting any scoped grant

`az role definition list --name Contributor` returns `Actions: ["*"]` with a `notActions` list that does **not** exclude `Microsoft.App/containerApps/delete` or `Microsoft.App/containerApps/listSecrets/action`. An action on a resource is authorized at that resource's *own* scope, so a `Contributor` assignment scoped to a single resource carries two consequences that are easy to assume away:

- **It can delete that resource.** `Contributor` on `datatap-rg/digichat` permits `Microsoft.App/containerApps/delete` on the **production digichat app**. It cannot *create* a new app — that needs the parent resource-group scope — but delete works from the resource's own scope. So the two ACA grants are the more dangerous of the grants on this list, not the safe ones.
- **It can read that resource's secret values.** See the inline-secrets section below. `listSecrets` returns values in cleartext.

On the ACR the registry is `roleAssignmentMode: LegacyRegistryPermissions`, where `Contributor` at registry scope covers registry control-plane operations including **delete the registry**, plus full data-plane access. Azure's least-privilege guidance points CI pushes at `AcrPush`, which carries no control-plane permission at all.

So the grants worth correcting, in order of severity:

1. `datatap-digichat-deploy`'s `Contributor` on **both ACAs** — can delete either Container App, and can read both apps' inline secrets. Replace with `AcrPush` for push and a custom role carrying `Microsoft.App/containerApps/read` + `/write` **without** `/delete` and **without** `listSecrets`.
2. `datatap-digichat-deploy`'s `Contributor` on the **whole ACR** — can delete repositories and the registry. Replace with `AcrPush`.
3. The inherited subscription-wide `Contributor` held by `datatap-web-github-deploy` — reaches `datatap-rg`, `datatap-dev-rg`, and any Key Vault or managed identity added later.

None of these is leaking today: all three principals are dormant, with no credential. They are latent grants, not active exposures.

**The prod app pulls with its own identity, not a stored password.** `registry.identity: "system"` on both ACAs, with no `registryCredentials` block and no `username`/`passwordSecretRef`. That part of the setup is correct and needs no credential registered here.

### Rotation path for the CI deploy identity

| Field | Value |
|-------|-------|
| **Owner** | Security (this document), with DevOps as the consumer |
| **Canonical store** | **None today.** The identity has no credential, so there is nothing to store. When lane B is chosen (see `docs/ops/digichat-datatap-aca.md` §1, decision pending), the store becomes the Azure app registration's **federated identity credential**, subject `repo:digithings-ai/digithings:environment:production` — a GitHub OIDC token minted per run from the `production` environment. **No client secret and no repo secret.** |
| **Refresh path** | There is no value to refresh. Rotation *is* revocation: delete the federated credential, re-create it against the same subject, and re-run. The 90-day value-rotation cadence does not apply to a federated credential — it has no secret value to copy. Instead the binding is re-issued whenever the subject's environment changes, and the app registration itself is reviewed quarterly. |
| **Staleness detector** | **None yet.** Add with the lane: a pre-flight step that asserts the workflow's OIDC subject matches an expected federated credential on the app registration, so a renamed environment fails loudly instead of silently losing write access. |
| **Required roles when created** | `AcrPush` on `datatapchatregistry` — **not** `Contributor`, which can delete repositories and the registry — plus a **custom** Container Apps role at `datatap-rg/digichat` granting `Microsoft.App/containerApps/read` and `/write` and **explicitly not** `/delete` or `listSecrets/action`. Do not reuse `datatap-digichat-deploy`'s app id. |

Note that `containerApps/write` is not an image-only permission: it permits changing env vars, command and identity on the app, which is code execution as the app's own managed identity. That is why `listSecrets` must be left out of the role — a compromised CI run should not be able to read the app's secrets on the way past.

### Lane-B CI credential — scoped, not created

**Status: not needed.** DIG-1242's lane question was answered on 2026-10-06: **Option A** (build lane only), so the pipeline never writes Azure and needs no federated credential. Nothing here has been created and no ARM write was made. DIG-1349, which would have built this, is moot unless the lane is revisited.

The spec is kept because choosing B later should be a single decision with no further design work:

| Item | Required shape |
|------|----------------|
| App registration | **New**, purpose-named (e.g. `datatap-digichat-deploy-oidc`), created in the DataTap tenant `ac621ee5-…`. Not `be54468d-…`, not `3f597b0e-…`. |
| Credential type | **Federated identity credential only.** OIDC, issuer `https://token.actions.githubusercontent.com`, subject `repo:digithings-ai/digithings:environment:production`, audience `api://AzureADTokenExchange`. |
| Secret material | **None.** No client secret, no certificate, no `AZURE_CLIENT_SECRET` repo secret. The workflow authenticates with `permissions: id-token: write` + `azure/login` with `client-id` only. |
| Roles | `AcrPush` on `datatapchatregistry` **and** the custom Container Apps role described above at `datatap-rg/digichat`. Neither may inherit from the subscription. |
| Bound to | The `production` GitHub environment, not a bare workflow ref or branch — so a branch or fork cannot exchange the token, and the environment's existing required reviewer stays in the path. A GitHub OIDC `sub` is a single string; the workflow file path is not a claim dimension, so the binding cannot be narrowed to a specific workflow file. |
| Detector | Pre-flight assertion that the workflow's OIDC subject matches an expected federated credential. The role-assignment audit runs **from the subscription `Owner` outside CI**, because `az role assignment list` needs `Microsoft.Authorization/roleAssignments/read`, which the CI credential deliberately does not hold. |
| Verification | After creation: push a test tag, confirm the image lands in `digichat`, and confirm no grant beyond the two above is inherited at either scope. |
| Retire | When it exists, delete `datatap-digichat-deploy` (`44cfda92-…`) and its three `Contributor` grants in the same change. Nothing should hold `Contributor` on an ACA or on the ACR once a push-only credential works. |

### Container App inline secrets — and yes, they are readable

Both ACAs declare exactly two secrets, and both hold **inline values** rather than referencing a Key Vault secret (`keyVaultUrl: null`, `identity: null` on the secret entry):

**Four bindings, not two.** Each ACA carries its own pair, and the prod and dev values **differ** (verified by fingerprint 2026-10-06, DIG-1344). Anything below that says "per app" is four credentials, not two.

| Secret name on the ACA | Env var | Owner | Canonical store | Refresh path | Detector |
|------------------------|---------|-------|-----------------|--------------|----------|
| `auth-secret` (prod, dev) | `AUTH_SECRET` | Chris Stefan | **The Container App itself** — `datatap-rg/digichat` and `datatap-dev-rg/digichat`. Inline value, `keyVaultUrl: null`. There is no Key Vault in the subscription, so this is the only copy. | Read the current value back with `az containerapp secret list --show-values`, edit it **outside the model**, then `az containerapp secret set -n digichat -g <rg> --secrets auth-secret=<new-value>` on **one** app, re-verify login on that app, then the other. Never pass `--secrets` to a promote. | `scripts/digichat_aca_secret_detector.py` — live fingerprint + inline-binding check, exit 1 on drift. |
| `embed-tenants` (prod, dev) | `DIGICHAT_EMBED_TENANTS` | Chris Stefan | **The Container App itself** — same shape. Carries the per-tenant embed `token` values. | Same, per app and per binding. | Same detector. |

**Fingerprints, not values** live in [`digichat-aca-secret-fingerprints.json`](digichat-aca-secret-fingerprints.json): a SHA-256 and a byte length per binding, plus owner, custody state and the expiry. A fingerprint is safe to commit and is enough to notice a value that changed — which is the only drift mode a single-copy inline secret actually has. The detector compares live values against it **inside the process**; no value is printed, returned, or written anywhere.

**Correction to an earlier statement on this issue.** DIG-1344 opened claiming the values had "no recovery path" and that `az containerapp secret list` returns "names and metadata, never values". That is wrong, and the paragraph below already said so: `--show-values` returns them in cleartext. The practical consequence is large — **no human needs to supply anything out of band.** Rotation does not depend on finding the original value, which removes the single thing that made this look unrecoverable.

### Store decision, and a contradiction recorded rather than hidden

Chris Stefan answered the DIG-1344 board card on 2026-10-06: holder = *"lives on the datatap-web repo"*, path = *`document`* (keep inline, no Azure change). Both parts were checked against the source before being written down:

- **`auth-secret` is not in that repo at all.** Zero matches in the working tree; the only hit in full history is a 2026-08-05 docs commit by Chris (`docs/superpowers/plans/2026-08-05-chat-access.md`) naming the variable in passing. The card's premise — that both values share one custody answer — does not hold.
- **The `DIGICHAT_EMBED_TENANTS` value in that repo is not the deployed one.** `DataTapStream/datatap-web` `README.md:51` carries a tracked `export DIGICHAT_EMBED_TENANTS=…`, first committed 2026-07-06 in `9e849f3`. It is a **320-byte local-dev placeholder** under a heading that reads *"Local digichat embed iteration"* (`http://127.0.0.1:3000/embed`), containing one token entry with the literal `local-dev-token`. The prod ACA value is **1112 bytes** and the dev value **1304 bytes**. Different fingerprints, not a reformat.
- **So the canonical store is the Container App, and `document` as chosen does not match reality.** It is recorded above as the ACA, because that is where the value provably lives.

A committed README is also **not an acceptable canonical store** under this file's own rules — the acceptable list is GitHub environment secret / Workers secret / Vault, and committing a real value is the thing `DIG-78` and `DIG-51` removed from `main`. The client's own repo is theirs to run as they like; what is not acceptable is quietly marking this compliant. It is written down as a dated exception instead:

> **Accepted exception (Chris Stefan, 2026-10-06).** The `datatap-web` README holds a *non-production* embed placeholder. It is not the canonical store for the deployed registry and must never be treated as one. If a real tenant token is ever committed there, that is a leak and a rotation trigger, not a documented store.

**Custody closed on the second card (Chris Stefan, 2026-10-06T12:41Z).** The first card asked one question about two secrets and got one answer that only covered `embed-tenants`; the CTO asked for a second card for the rest. Chris answered it: accountable holder for `auth-secret` = **Chris Stefan**, canonical store = **the Container App**. Both cards are now `answered`, so this record is a decision and not an assumption:

- **Owner** for all four bindings (two secrets x prod + dev) is **Chris Stefan**, as recorded in the table above.
- **Canonical store** is the Container App itself. Confirmed by the answer *and* by the fingerprint evidence — the only provable location of each deployed value. This supersedes `path = document` from the first card for the deployed values; that answer describes the client's repo, which holds only a non-production placeholder (see the accepted exception below).
- **No ARM write was made and none is pending.** Keeping the ACA as the store means no Key Vault is created, no role is granted and no value moves, so nothing waits on a DataTap tenant `Owner` account. Rotation stays an agent-executable operation because the values are readable.

**What this does not settle:** whether the ACA is still the store after `2027-01-04`, and the `listSecrets` blast radius below. Both are DataTap-side ARM decisions and are recorded as open items, not as custody gaps.

**The values are recoverable, and that changes the risk.** `Microsoft.App/containerApps/listSecrets/action` returns secret values in cleartext — the CLI exposes it as `az containerapp secret list --show-values`, and `Contributor`'s `Actions: ["*"]` covers it with no `notActions` exclusion. So any principal that can authenticate and holds `listSecrets` on the app can read `AUTH_SECRET` and every `DIGICHAT_EMBED_TENANTS` token in plaintext.

Who that is today: **only the shared subscription-`Owner` account can authenticate** — all three service principals are dormant with no credential. So the shared account is a single point of compromise for both secrets *and* for deletion of either Container App. That is the finding that matters, and it is why "nobody else can read it" is not the reassuring answer it looks like.

`az keyvault list` on the subscription returns `[]` — there is no Key Vault in it. As of 2026-10-06 (DIG-1344) the four bindings therefore have an owner, a canonical store (the Container App itself), a working refresh path, a fingerprint lock file and a failing-loud detector, and an expiry of **2027-01-04**. They are production-ready on the letter of this file's rule. The blast radius is unchanged and is a separate, open item: `listSecrets` is still handed out by the `Contributor` grants above, so adding a Key Vault would not by itself fix the read path — the durable fix is Key Vault references on the app **plus** a custom role that omits `listSecrets`. That is an ARM write on a client production resource and is a DataTap-side decision.

`AUTH_URL` and `DIGICHAT_ENABLED_SERVICES` are also set on both ACAs but come from `secretRef: null` — plain configuration, not secrets. They are not registered here.

### Registry hygiene

`datatapchatregistry` holds exactly one repository, `digichat`, with 33 tags — no other image.

| Setting | Value | Why it matters here |
|---------|-------|--------------------|
| `adminUserEnabled` | `false` | No shared admin password to leak. Good. |
| `anonymousPullEnabled` | `false` | No unauthenticated pull. Good. |
| `publicNetworkAccess` | `Enabled` | The registry is reachable from the public internet; `networkRuleSet` is `null`, so there is no IP allow-list. |
| `roleAssignmentMode` | `LegacyRegistryPermissions` | This is the mode that decides what `Contributor` means above — admin credentials govern registry-level access, RBAC governs token-based access. |
| `exportPolicy` | enabled | Images can be exported out of the registry by anything with the data-plane permission. |
| `retentionPolicy` | **disabled** (7 days configured 2026-07-16, never enabled) | Every tag stays pullable forever. |
| `softDeletePolicy` / `quarantinePolicy` / `trustPolicy` | all disabled | A deleted tag leaves no recovery window, and no scanning gate on push. |

With retention disabled, all 33 tags stay pullable forever, including the two deliberate `v0.9.1-textleak-68d945ce` / `…-amd64` leak-test builds sitting in the production registry. Enabling retention, and adding a trust-policy scan gate for pushes, are policy changes on a client registry — proposals for DataTap, not things to apply from here.

---

## Other Hand-Held Credentials

| Credential | Owner | Canonical Store | Refresh Path | Detector |
|------------|-------|-----------------|--------------|----------|
| ACA inline `auth-secret` / `embed-tenants` — 4 bindings (DataTap ACA, prod + dev) | Chris Stefan (confirmed by board answer, 2026-10-06) | the Container App itself, confirmed by board answer (no Key Vault exists in the subscription) | read back with `az containerapp secret list --show-values`, then `az containerapp secret set -n digichat -g <rg> --secrets <name>=<new-value>` on one app at a time | `scripts/digichat_aca_secret_detector.py` — fingerprints in [`digichat-aca-secret-fingerprints.json`](digichat-aca-secret-fingerprints.json), expiry 2027-01-04 (see [above](#container-app-inline-secrets--and-yes-they-are-readable)) |
| `POLICY_CHECK_APP_PRIVATE_KEY` — the policy-check gate reader: GitHub App `policy-check-reader`, `digithings-ai/digithings` only, `Administration: read` only. **Scoped, not created.** | Security team (Chris Stefan as the create-and-install backstop — creating an org App is an owner action) | Planned: GitHub Actions `cron` environment secret, one home, **no Bitwarden copy**. GitHub Actions is the only consumer and write-only access to a secret is all it needs, so a second copy would be a second way to lose the credential. | Create the App from [`.github/policy-check-reader-app.json`](../../.github/policy-check-reader-app.json), install it on this repo, generate a private key, `gh secret set POLICY_CHECK_APP_PRIVATE_KEY --env cron`, smoke it with `python3 scripts/mint_policy_check_token.py --verify`, then delete the previous key **last**. On a suspected leak, **uninstall the App first** — deleting only the exposed key leaves the App able to mint. | **Scoped, not live.** The drift guard that would consume it is DIG-2098 decision D; until that lands there is no failing-loud check, so by the Enforcement rule below this row is a specification, not a production-ready credential. Full runbook: [`policy-check-credential.md`](policy-check-credential.md) |

---

## Adding a New Credential

1. Assign an **owner** (team, not individual).
2. Choose **one canonical store** (GitHub environment secret, Cloudflare Workers secret, Vault, etc.).
3. Document the **refresh path** (exact CLI command or UI steps).
4. Ensure a **staleness detector** exists (pre-flight check, canary, scheduled validation) — file a ticket if not.
5. Add a row to the table above and a runbook entry in this file.
6. Update `.env.example` with a comment pointing to the canonical store (never commit real values).

---

## Enforcement

- **No duplicate stores**: A credential must not be written to multiple independent stores (e.g., both GitHub secret and local `.env` as production sources).
- **No secret values in docs**: This file and `.env.example` document *names* and *processes* only. Real values never appear here.
- **Fingerprints are not values**: a SHA-256 plus a byte length per binding (see [`digichat-aca-secret-fingerprints.json`](digichat-aca-secret-fingerprints.json)) is the accepted way to make a single-copy secret drift-detectable without holding it. It is a one-way digest of a high-entropy value, not the value.
- **No secret values in any chat surface** — not in an issue, a comment, an interaction reason, a ticket, or a chat, and not by the credential owner. See [Never paste a credential value](#never-paste-a-credential-value). An interaction reason in particular is **not editable and not deletable** once written, so a value pasted there is permanent.
- **Detector required**: Every credential must have a failing-loud check. If the detector doesn't exist, the credential is not production-ready (see `DIG-345` for the Gloomberb detector).
- **Reach is enforced, not remembered**: the DataTap Azure access register ([`config/datatap_azure_access_register.json`](../../config/datatap_azure_access_register.json)) is enforced by [`scripts/az-guard/az`](../../scripts/az-guard/az), which refuses every `az` command aimed at a subscription that is not on it. Runbook, install, rollback and the limits of that control: [`datatap-azure-az-guard.md`](datatap-azure-az-guard.md) (DIG-1725). The register is empty, so every `az` command is refused today — including the `az …` commands quoted elsewhere in this file.
