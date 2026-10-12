# PR #5157 — Counsel sign-off on Gloomber Terms classification

**Scope:** `docs/vendor-terms/gloomber/**` (new artefact archive + INDEX record), the redaction of the
session-cookie acquisition method from `docs/ops/gloomberb-session-cookie.md` and
`docs/superpowers/plans/2026-09-16-gloomberb-session-cookie-runbook.md`, and the new
`## Vendor terms and what this file may publish (DIG-1194)` section in `docs/ops/SECRETS_INVENTORY.md`.

**Reviewer:** Counsel (`0e57e884-0920-4d5f-a17b-a94a98fb29d9`)
**Author of the change:** Security (DIG-1194)
**Branch:** `task/1194-vendor-terms-and-vendor-row` · **Base:** `develop`
**Date:** 2026-10-05
**Gate:** `docs/VENDOR_CONTENT_BOUNDARY.md` step 5 — escalate on Prohibited or Unclear, do not merge
until Counsel signs off in writing.

**Counsel memo:** [`docs/vendor-terms/gloomber/COUNSEL-2026-10-05-session-cookie-position.md`](../vendor-terms/gloomber/COUNSEL-2026-10-05-session-cookie-position.md)

## Artefact verification

| Check | Result |
|---|---|
| HTML artefact hash matches INDEX row | `6f781a39…a0fc` — match |
| Text extract hash matches INDEX row | `0cd96156…265f` — match |
| Source, retrieval timestamp, effective date recorded | `https://gloom.sh/terms`, `2026-10-05T20:34:28Z`, effective 2026-09-26 |
| Clauses quoted verbatim in the position | Pass |
| Vendor row recorded in INDEX in the same PR (step 6) | Pass |

Both hashes re-verified locally with `shasum -a 256` on 2026-10-05.

## Review checklist

| Area | Finding | Status |
|---|---|---|
| Classification correctness | "Unclear" split into four per-method outcomes; **prohibited** for cookie replay | Corrected, see below |
| §14 licensing gap | Org internal use licensed only **under a team plan**; we have none. **An API key does not cure it.** | **Against us — CONFIRMED** |
| §11 carve-out | Conjunctive test. Second conjunct ("within the limits we offer") fails on its own for a cookie | **Prohibited — CONFIRMED** |
| §11 delay limb | Verb is *interfere with*; on a free plan the delay **is** the offered limit | Does not bite — CONFIRMED |
| §4 redistribution / hosted tripwire | Clean today. §12 permits apps only "for yourself **or for users who have their own access**" | Pass with tripwire recorded |
| §2 MIT licence | Applies to source code, not "the data and content we provide" | Does not help us |
| Acquisition method removed, client contract kept | Correct line: our client contract is our own fact; acquisition is the exposure | Pass |
| Citation correction | `client.py:403-407` correct; the old `client.py:180-183` citation was wrong and had propagated into DIG-1194 | Pass — good catch |
| Publication exposure reasoning | Gloomberb has **no** material-breach escalation clause; Prime Terminal's reasoning is **not portable** | Corrected, see below |
| Git history decision | No rewrite. 19-day window; a public rewrite achieves nothing and costs the audit trail | Counsel decision, recorded |
| Publishing the terms archive | Public legal document, fair dealing, no confidentiality clause. §2 is a **non-grant**, not a prohibition. Our own step 2 requires committing it | No meaningful counter-exposure |
| `SECRETS_INVENTORY.md` Q1–Q3 | Generalise the method, keep the names and `file:line`; remove the one acquisition sentence; keep the negative finding | Pass |
| Status banner accuracy | Was `UNCLER` (typo) and "Counsel sign-off pending" | **Two corrections required, made** |

## Corrections made before approval

Both are one-line edits inside this PR's own diff. Had they not been made this would have been a
**block** naming these two specific required changes:

1. `docs/ops/gloomberb-session-cookie.md:21` read **`UNCLER`** in the compliance-status banner. A typo,
   sitting in the one line a reader will quote, in a PR whose purpose is to make the compliance record
   accurate. Now states the Counsel classification per access method.
2. The same banner said "Counsel sign-off pending" with no memo reference. Now names the memo, the date
   and the per-method classification, so a reader of the runbook lands on the position.

## Two corrections to the PR's own framing

Both make our position **stronger**, not weaker. Stated here so the CTO hears the corrected version.

1. **The §11 hinge is not the contested conjunct.** The carve-out requires access "through the
   interfaces" **and** "within the limits we offer for that purpose". The analysis treated the first as
   arguable in both directions. The second fails independently: a session cookie cannot be scoped per
   integration, rate-limited per integration, monitored as a key, or revoked without killing a human's
   live session — which is why §12 specifies keys. **We do not need to win the contested argument.**
2. **The delay question does not separate a documentation defect from a live breach.** The
   classification does not move on the billing fact. The open billing question is real but
   **financial** (§8 trials require a payment method and auto-convert), not a classification blocker.

## Residual risk (tracked, not accepted here)

| # | Risk | Owner | Note |
|---|---|---|---|
| 1 | `GLOOMBERB_ENABLED` still defaults **ON** | digifetch / Security | Counsel step 1. Doable today, no credential needed |
| 2 | Credential not yet destroyed | Security | Needs a Gloomber account session; blocked on `dt-login` / Bitwarden (DIG-95) |
| 3 | Account not yet closed | Security, after Chris answers | Only server-side revocation. **Check billing state before delete** (§15 no refund, §9, §8) |
| 4 | §14 unresolved for the **47 anonymous** tools | Security | They need no credential; closing the account does not fix them |
| 5 | Hosted-surface tripwire | Security + Counsel | §12 "users who have their own access". Needs a **fresh** review, not this memo |
| 6 | "Gloomberb" data-source label | OSS Researcher | Deferred to `task/1132-license-trademark-fix`. Counsel reads it as descriptive reference, arguably inside the §2 carve-out. Do not block on it |

## Git history

**Decision: do not rewrite.** The acquisition recipe was in published `develop` from **2026-09-16**
(commit `9ac0eea84`, merged) to **2026-10-05** — 19 days. A public-repository rewrite does not achieve
confidentiality: forks, clones, CI caches and everyone who read it retain the content, and our own
boundary document says "GitHub does not truly delete history". It would destroy the audit trail the
change-traces-to-an-issue discipline depends on, and in a dispute it would read as evidence destruction
to a HKIAC arbitrator while we owe Cold Start an uncapped §18 indemnity. The redaction commit stands, and
the memo records the window, the choice and the reasons so the decision is auditable.

## How this sign-off was recorded

GitHub rejected a native `APPROVE` review — *"Can not approve your own pull request"* — because the API
token available to Counsel belongs to the PR author. The sign-off is therefore a formal `COMMENT` review
on PR #5157 plus this artefact, **not** a GitHub approval, and the `reviewed:agent` label is for the PR
owner to apply. Recorded openly rather than presented as a stronger gate than it is.

**Sign-off:** The vendor-terms record and the exposure reduction in #5157 are acceptable to merge to
`develop`. Boundary step 5 is satisfied. **This approval covers this PR only** — it approves no new
Gloomber access work. Cookie replay and every unauthorised method remain **prohibited** until a team
plan or a written agreement under §21 resolves §14.