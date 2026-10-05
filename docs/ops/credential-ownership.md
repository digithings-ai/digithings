# Credential Ownership & Refresh Paths

> **Rule** (per `client-incidents.md` §9): *Any credential we hold by hand needs one owner, one refresh path, and a check that fails loudly when it is stale.*

This document registers every hand-held credential in the digithings monorepo with its **owner**, **canonical store**, **refresh path**, and **staleness detector**. No credential should exist in more than one canonical store.

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

---

## Other Hand-Held Credentials

*This section is a placeholder for future credentials. Add entries here following the same schema.*

| Credential | Owner | Canonical Store | Refresh Path | Detector |
|------------|-------|-----------------|--------------|----------|
| — | — | — | — | — |

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
- **Detector required**: Every credential must have a failing-loud check. If the detector doesn't exist, the credential is not production-ready (see `DIG-345` for the Gloomberb detector).
