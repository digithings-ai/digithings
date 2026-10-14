# Repo-split history-preserving extraction scripts (DIG-3569)

Dry-run-only tooling for the digithings 8-repo split (parent epic DIG-3518).
Extracts each of R1–R7 with git history from a throwaway local clone, driven by
the move lists from DIG-3562–DIG-3568 (leaves E–K).

HARD LIMITS (board orders, Chris 14 Oct): planning, dry runs and PRs into
`develop` only. NO repo creation on Cursor Origin or GitHub, NO migration/push
of history, NO Cloudflare config changes, NO `main` merges, no Paperclip restart.
Anything needing those goes to Chris as a decision.

## Layout

- `move-lists/r1.paths … r7.paths` — one repo-relative path per line (`#` comments
  allowed). Directories keep the whole subtree. Verified present at
  `github/develop d227b6ed5` (2026-10-14) by `dry-run.sh`.
- `move-lists/r5.drop` — second-pass removals from the R5 extraction (the 10 OCC
  seed files that move to R6), applied as `filter-repo --invert`.
- `move-lists/overlaps-known.txt` — documented cross-repo overlaps (see below).
- `dry-run.sh [REF] [REPO]` — validates every move-list path exists at REF.
  No clone, no rewrite. This is the fast gate (also the local test pass).
- `check-overlaps.sh [REF]` — expands every move list to a file list at REF and
  reports files claimed by two repos. Known overlaps pass; anything new fails.
- `extract-one.sh <rN> <SRC> <DEST> [REF]` — full extraction of one repo:
  `git clone --no-local` (copy, source untouched) into a throwaway DEST, then
  `git filter-repo` keep-pass (+ drop-pass for R5), then a report line
  (commits, files, worktree KB, git KB, gitleaks hits). DEST must be under
  `$PAPERCLIP_RUN_SCRATCH_DIR` or `/tmp`; refuses existing DEST; never pushes
  (no remote is ever added — the clone carries the source remote, push is simply
  never invoked, and DEST is deleted after the run).
- `extract-all.sh <SRC> <OUT> [REF]` — all seven in plan migration order
  (R6, R7, R1, R2, R3, R5, R4; repo-split.md section 5 step 2), each from a fresh
  full clone, plus a combined `report.tsv`.

## Known overlaps (both extractions carry the file in dry runs)

- R1/R2 `digiquant/scripts/{generate_tearsheets,export_sdca_macro,plot_sdca_tearsheet}.py` —
  R1 wins at migration (plan extracts R1 before R2); R2 executor drops them.
- R3/R4 `.github/workflows/test-web.yml` — shared lane; each repo keeps its section
  (split at migration, per DIG-3565).
- R5/R6 `scripts/{verify_occ_invite_key,test_verify_occ_invite_key}.sh`,
  `scripts/occ_invite_key_fixture_server.mjs` — guard R5+R6 surfaces (DIG-3566 F13);
  ruling owed by DIG-3567 (R6 owner).

## Delivered inputs (J/K landed 14 Oct)

R6 follows DIG-3567 (done), R7 follows DIG-3568 (in_review); both re-verified
path-by-path at `github/develop d227b6ed5` by these scripts' own gates. Three
ref-specific discrepancies were measured while regenerating and are recorded in
`move-lists/r6.paths` notes 1-3 (`start_digiseed.sh` name miss, devkit-looks
presence, occ_help 4-vs-6 count). The R5/R6 double-claim on 9 rollout scripts +
runbook (DIG-3566 E.1/F13 vs DIG-3567 section D) is recorded in
`overlaps-known.txt`; the ruling is owed by those owners, not resolved here.

## Open decisions blocking a real migration (not this leaf)

D-R5-1 image direction, D-R5-2 self-host parity home, D-R5-3 zammad public/private,
`config/byok-providers.json` dual-consumer ownership (DIG-3563 section 6.1),
`config/contract/` gate split. None are resolved here.

## Local test pass (no GitHub Actions — minutes exhausted, per Chris 14 Oct)

```
./dry-run.sh github/develop ~/Code/digithings
./check-overlaps.sh github/develop   # run inside a digithings checkout
bash -n *.sh
```

Record the output in the PR body.
