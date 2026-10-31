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
is the argument for retiring the client desk-session handoff (DIG-1226, action 5).

The client's own rule for this credential path is kept in the private client repo, not in R0.

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

## Client tenant credentials (moved out of R0, 2026-10-31)

Per-client cloud tenant detail is not recorded in R0. That covers subscriptions, service principals and managed identities, container registries, tenant accounts, and inline container secrets with their custody decisions. It is kept in the private client repo (`digithings-ai/<client-slug>`) and in the owner's Records. This section held that detail until 2026-10-31; it was removed because R0 is public.

The rule at the top of this file still applies to anything digithings hands into a client tenant: one owner, one refresh path, and a check that fails loudly when it is stale. Every `az` command aimed at a subscription that is not on the access register is refused by [`scripts/az-guard/az`](../../scripts/az-guard/az).

---

## Other Hand-Held Credentials

| Credential | Owner | Canonical Store | Refresh Path | Detector |
|------------|-------|-----------------|--------------|----------|
| Per-client container secrets (client tenants) | Chris Stefan | tracked in the private client repo / owner Records, not in R0 | per the client repo's runbook | per the client repo's runbook |
| `POLICY_CHECK_READER_TOKEN` — the policy-check gate reader: fine-grained PAT `digithings-policy-check-reader`, `digithings-ai/digithings` only, `Administration: read` only, 90-day expiry. **Scoped, not created.** A GitHub App was recommended first and declined on 2026-10-07 — see [`policy-check-credential.md`](policy-check-credential.md). | Security team (Chris Stefan as the create-and-revoke backstop — a PAT is issued from his personal account, and on a one-member org that account is the org owner, so it is a red line for agents) | Planned: GitHub Actions `cron` environment secret, one home, **no Bitwarden copy**. GitHub Actions is the only consumer and write-only access to a secret is all it needs, so a second copy would be a second way to lose the credential. | Chris creates the token (`digithings`, one repository, `Administration: read`, 90 days), then `gh secret set POLICY_CHECK_READER_TOKEN --env cron --repo digithings-ai/digithings` from **stdin**, then `gh secret list --env cron` to prove it landed at that scope, then smoke it with `GH_TOKEN=… gh api repos/digithings-ai/digithings/branches/develop/protection/required_status_checks`, then revoke the previous token **last**. On a suspected leak, **revoke first** — it is per-token, so `GH_DISPATCH_TOKEN` is untouched, and revocation is a personal-account action, so it waits on Chris. | **Scoped, not live.** The credential does not exist: `gh secret list` has no `POLICY_CHECK_*` at any scope. The drift guard that would consume it is DIG-2098 decision D; until that lands there is no failing-loud check, so by the Enforcement rule below this row is a specification, not a production-ready credential. Full runbook: [`policy-check-credential.md`](policy-check-credential.md) |

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
- **Reach is enforced, not remembered**: [`scripts/az-guard/az`](../../scripts/az-guard/az) refuses every `az` command aimed at a subscription that is not on the access register. Its runbook sits next to this file in `docs/ops/`.
