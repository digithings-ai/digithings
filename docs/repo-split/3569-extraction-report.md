# DIG-3569 — extraction dry-run report (R1–R7)

Scripts: `scripts/repo-split/` (this PR). Move lists: DIG-3562–DIG-3566 plan
documents (E–I); R6/R7 provisional from repo-split.md (DIG-3567/DIG-3568 still
`in_progress`, no inventory docs yet). Method: fresh throwaway clone per repo
(local hardlinks, source untouched) at `github/develop d227b6ed5`, then
`git filter-repo` keep-pass (+ drop-pass for R5), then report. No remotes added,
nothing pushed, clones deleted after the run.

## Results

| repo | commits | files | worktree KB | git KB | gitleaks hits |
|---|---|---|---|---|---|
| R1 digiquant-strategies | 488 | 114 | 151,068 | 149,852 | 0 |
| R2 digiquant-stack | 1,441 | 489 | 155,556 | 151,000 | 8 |
| R3 digiquant-web | 333 | 231 | 166,436 | 164,824 | 0 |
| R4 digithings-web | 446 | 273 | 155,284 | 152,172 | 0 |
| R5 digithings-stack | 842 | 185 | 152,316 | 150,356 | 4 |
| R6 digichat-tenants | 104 | 30 | 148,992 | 148,708 | 2 |
| R7 twelve-x additions | 90 | 122 | 149,804 | 148,776 | 0 |

File counts match the leaf inventories within triage deltas (R2 489 vs 432+
untriaged research dir now included; R5 185 = 47+12+11+39+4+19+16+6+3+1+23
docs/ops candidates + 4 workflows).

## Gitleaks findings (rule + file + line only — no values recorded)

All 14 hits are `generic-api-key` in test/fixture/example files. Values were not
compared against live secrets (handling them is forbidden); none is assessed as
a live credential here.

- R6 `scripts/test_verify_occ_invite_key.sh:19` (2 commits) — key-shaped fixture
  in a test script. Standing rule (Chris, 14 Oct) says test keys are generated at
  runtime, never committed: this file violates it. Owner: DIG-2779 / DIG-3567.
- R2 `digiquant/src/digiquant/research/config/mcp.secrets.env.example:5,7,9`
  (2 commits) — example values in an `.example` file. Owner: R2 executor.
- R2 `digiquant/supabase/functions/settings/settings.test.ts:241,359`
  (2 commits) — vault-key-shaped test constants. Owner: R2 executor.
- R5 `scripts/test_occ_rollout_scope_guard.sh:35,36` (2 commits) — `NEW_KEY`/`KEY2`
  fixtures (previously noted in the Gloomberb session-gate work). Owner: DIG-2779.

Routed, not fixed here (rule 3; Secrets/Security lanes own remediation).

## Gates run (local — GitHub Actions minutes exhausted, per Chris 14 Oct)

- `dry-run.sh github/develop`: all 7 repos, 0 missing paths.
- `check-overlaps.sh github/develop`: 10 EXPECTED r5/r6 seed overlaps (removed by
  the r5.drop second pass) + 3 KNOWN script overlaps; 0 unlisted. Exit 0.
- `bash -n` on all four scripts. Exit 0.
- Full `extract-all.sh` above: 7/7 extractions completed, report written.

## Not done (hard limits)

No repo created on Origin/GitHub, no history pushed, no Cloudflare changes, no
`main` merge. Open migration decisions (D-R5-1/2/3, byok-providers ownership,
`config/contract` split, R6/R7 provisional lists) are recorded in
`scripts/repo-split/README.md`, not resolved.
