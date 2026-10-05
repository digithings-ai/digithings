# Credential Ownership Policy

**Status**: Mandatory  
**Applies to**: All hand-held credentials across digithings, twelve-x, and client repos  
**Authority**: Platform team  
**Reference**: client-incidents.md §9

---

## The Rule

> **Every hand-held credential has exactly one owner, one refresh path, and one stale-detection check.**

No exceptions. No shared custody. No "it lives in two places."

---

## What This Means

| Property | Requirement |
|----------|-------------|
| **Owner** | A single team (not a person) is named as the owner. The owner is responsible for rotation, revocation, and incident response. |
| **Refresh Path** | Exactly one automated or documented manual process refreshes the credential. The path is tested and owned. |
| **Stale Detection** | Exactly one mechanism (cron job, monitoring alert, expiration check) detects when the credential is stale or expired. |

---

## Current Credential Inventory

| Credential | Owner | Source of Truth | Refresh Path | Stale Detection |
|------------|-------|-----------------|--------------|-----------------|
| `GLOOMBERB_SESSION_COOKIE` | Platform | GitHub Actions `cron` environment secret (digithings repo) | `scripts/refresh_session_cookie.sh` (writes to GitHub secret) | CI job validates cookie freshness on each cron run |
| `PRIMEMARKET_SESSION_TOKEN` | Platform | GitHub Actions secret (twelve-x repo) | `scripts/refresh_session_cookie.sh` (twelve-x repo; verifies live then writes secret) | `primemarket_session_heartbeat.yml` (twice-daily) — **known gap**: verify can pass while pmt endpoints 401 |
| `DIGIQUANT_VAULT_MASTER_KEY` | Platform | Platform secret store (1Password/Bitwarden) | Manual rotation via Platform runbook | None yet — **gap** |
| `LITELLM_MASTER_KEY` | Platform | Platform secret store | Manual rotation via Platform runbook | None yet — **gap** |
| `OPENAI_API_KEY` / `XAI_API_KEY` / etc. | Platform | Platform secret store | Vendor rotation + Platform sync | Vendor expiration notices |

> **Note**: This table must be kept current. Add new credentials here when introduced. Remove when deprecated.

---

## Enforcement

1. **No credential may be added to `.env.example` without an entry in this table.**
2. **No credential may have two "source of truth" entries.** If a credential appears in both a GitHub secret and a local `.env`, the GitHub secret wins for production; `.env` is explicitly labeled "developer convenience only."
3. **The Platform team reviews this file quarterly** (aligned with client-incidents.md §9 review cadence).
4. **Any gap in stale detection is a P1 bug** — file an issue immediately.

---

## Adding a New Credential

When introducing a new hand-held credential:

1. **Assign an owner team** (Platform, Security, or a named product team).
2. **Choose one source of truth** (GitHub secret, platform secret store, vendor portal).
3. **Document the refresh path** (script, manual runbook, vendor auto-rotation).
4. **Implement stale detection** (cron validation, monitoring alert, vendor webhook).
5. **Add a row to the table above** and update `.env.example` with the ownership comment pattern.
6. **Get Platform team sign-off** before merging.

---

## Pattern for `.env.example` Comments

```bash
# <Credential name> for <purpose> (<issue/PR ref>).
# Single source of truth: <location> (<environment>).
# Local .env is optional developer convenience only — never committed.
# <Owner team> owns the credential and its refresh (see docs/ops/credential-ownership.md).
# <CREDENTIAL_NAME>=
```

**Example** (from `GLOOMBERB_SESSION_COOKIE`):

```bash
# Gloomberb session cookie for the session-gated digifetch tools (#4099).
# Single source of truth: GitHub Actions `cron` environment secret (production runs).
# Local .env is optional developer convenience only — never committed.
# Platform team owns the credential and its refresh (see docs/ops/credential-ownership.md).
# GLOOMBERB_SESSION_COOKIE=
```

---

## Related Documents

- `docs/ops/gloomberb-session-cookie.md` — Extraction and placement runbook for the Gloomberb cookie (digithings)
- `../twelve-x/docs/PRIMEMARKET_DESK_API.md` — PrimeMarket desk API and session runbook (twelve-x)
- `../twelve-x/scripts/refresh_session_cookie.sh` — Automation that verifies live then writes GitHub secret (twelve-x repo)
- `client-incidents.md §9` — Incident response playbook requiring credential ownership audit
- `SECURITY.md` — General security posture and secret handling

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-10-05 | Added `PRIMEMARKET_SESSION_TOKEN` (twelve-x) — single owner, refresh path, stale detection per DIG-377 | Platform team |
| 2026-10-04 | Initial version — establishes single-owner rule per DIG-377 resolution | Platform team |