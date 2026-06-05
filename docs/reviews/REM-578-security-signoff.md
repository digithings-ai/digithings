# REM-131 — Security-reviewer sign-off (PR #578 auth delta)

**Scope:** DigiKey revocation blocklist (REM-005–019), DigiChat embed gate (REM-010), execute_python fail-closed docs (REM-012).

**Reviewer:** security-reviewer subagent / human security review  
**Branch:** `task/577-audit-wave0-remediation`  
**Date:** 2026-06-05

## Checklist

| Area | Finding | Status |
|------|---------|--------|
| JWT `jti` blocklist + Redis | Fail-closed when `DIGIKEY_REQUIRE_BLOCKLIST=1`; startup rehydrate from `jti_issued` | Pass |
| Revoke endpoint | 503 when blocklist required but Redis unset | Pass |
| BFF session `jti` persistence | `JtiIssuedRow` on exchange | Pass |
| DigiChat embed | `DIGICHAT_EMBED_ENABLED` / `X-Embed-Token`; 503 when unset on embed routes | Pass |
| execute_python | Documented dev-only; subprocess static reject list | Pass (dev-only accepted) |
| Olympus RLS | Threat model doc only; no policy change (REM-035) | Pass with note |
| BFF Supabase redesign | REM-036 deferred — human gate | N/A this PR |

## Residual risk (tracked)

- REM-036: full Olympus BFF auth redesign — separate PR after threat model ADR.
- REM-104: token endpoint rate limit per API key prefix — follow-up.
- MCP `workflow` tool scope (REM-138): documented; enforce in deployment config.

**Sign-off:** Auth delta in #578 is acceptable to merge to `develop` with REM-036 explicitly deferred.
