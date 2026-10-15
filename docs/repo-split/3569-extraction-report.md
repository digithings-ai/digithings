# DIG-3569 — extraction dry-run report, rev 3 (send-back applied)

Scripts: `scripts/repo-split/` (this PR, rev-3 commit). Move lists follow the
accepted plans: R5 rev 6, R1 rev 4, R2 rev 2, R3 rev 3, R4 rev 3, R6 rev 2.
Call (a) applied (`apps/dashboard` net of the R7 hold → R3; digiquant core
pipeline + `config/contract/secrets.yaml` → R2). R7 is on HOLD: no list, no
extraction. Zero `.github/*` paths anywhere (global rule, mapping in DIG-3605).
No whitelist: `check-overlaps.sh` fails on any double claim (drop-aware: each
repo's `.drop` second-pass removals are subtracted before intersecting).

Method: fresh throwaway clone per repo at `github/develop d227b6ed5` (local
hardlinks, source untouched), `git filter-repo` keep-pass (+ `.drop` invert
pass), single-branch isolation (all other refs deleted — a real split carries
one branch), no remotes. Nothing pushed; clones deleted after the run.

## Results

| repo | commits | files | content bytes (HEAD) | history bytes (floor) | gitleaks |
|---|---|---|---|---|---|
| R1 digiquant-strategies | 406 | 111 | 953,253 | 242,103 | 0 |
| R2 digiquant-stack | 1,432 | 515 | 4,461,183 | 1,077,972 | 8 |
| R3 digiquant-web | 122 | 736 | 3,682,555 | 131,998 | 3 |
| R4 digithings-web | 369 | 269 | 2,520,452 | 474,041 | 0 |
| R5 digithings-stack | 743 | 176 | 1,423,835 | 861,870 | 0 |
| R6 digichat-tenants | 275 | 38 | 566,035 | 287,969 | 0 |
| R7 twelve-x | HELD | HELD | HELD | HELD | HELD |

Sizes are logical bytes, not disk: content = HEAD blob bytes
(`git cat-file --batch-check`); history = reachable-object bytes present
locally (a floor — a partial clone may lack some historical blobs, which are
skipped, never fetched). This supersedes rev 2's `du` figures, which
double-counted hardlinked/promisor packs and read a uniform ~150 MB everywhere.
Count controls: R3's 122 cross-checked at source (19 digiquant-web + 40
dashboard-net touching commits); twelve-x leftovers 0; R2 net 515 = doc 480 +
rev-1 §1.7 root items (Dockerfile, root ops scripts, config jsons).

## Gitleaks findings (rule + file + line only — no values recorded)

11 hits, all `generic-api-key` in test/fixture/example files. Values were never
compared against live secrets (handling them is forbidden); none is assessed as
a live credential here. All sit in extracted *history*; J rev 2 verified the
OCC test files clean at tip (runtime-generated keys), and R2 §5.5 makes two
fixtures runtime-generated — the tip direction is set, the history rows below
are the record, not new exposure.

- R2 `digiquant/src/digiquant/research/config/mcp.secrets.env.example:5,7,9`
  (2 commits) — example values. Owner: R2 executor.
- R2 `digiquant/supabase/functions/settings/settings.test.ts:241,359`
  (2 commits) — vault-key-shaped test constants. Owner: R2 executor.
- R3 `apps/dashboard/components/why/deliberations-tab.test.tsx:17,46` and
  `apps/dashboard/lib/pipeline-graph-data.test.ts:9` (1 commit) — test
  constants arriving with the new `apps/dashboard` scope. Owner: R3 executor.

Routed, not fixed here (rule 3; Secrets/Security lanes own remediation).

## Gates run (local — GitHub Actions minutes exhausted, per Chris 14 Oct)

- `dry-run.sh github/develop`: 6/6 repos, 0 missing paths
  (r1 111, r2 515, r3 736 net, r4 269, r5 176, r6 38 files).
- `check-overlaps.sh github/develop`: 0 double claims. Exit 0. (Caught one real
  leftover mid-run — `generate_tearsheets.py` in r1 — fixed before measuring.)
- `bash -n` on all four scripts. Full `extract-all.sh` at d227b6ed5: 6/6
  extractions completed, single-branch, no remotes; smoke re-ran the final
  script version end to end on r6.

## Not done (hard limits)

No repo created on Origin/GitHub, no history pushed, no Cloudflare changes, no
`main` merge. Open for owners: R5/R6 seed-script ruling is settled (R6 owns,
R5 keeps `seed_chroma.sh`); `infra/local-proxy/Caddyfile` contested (H7)
unassigned and excluded; `devkit-looks.*` stays R0; in-file carve-outs
(`optimize.py` SDCA parts, `DIGI_TENANT_CORPUS_MAP` block) belong to
refactor leaves, not to these path lists.
