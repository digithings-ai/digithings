# Stranded work and backup report — 2026-10-06

Agent: DevOps. Issue: DIG-1550. Snapshot cadence: every 30 min via launchd (`dt-snapshot`).

## 1. Snapshot loop — healthy

`~/.config/digithings/snapshot.log` last entry `2026-10-06 20:58:42` ("Nothing new to back up").
Cadence intact all day: 16:11, 16:42, 17:13, 17:43, 18:14, 18:45, 19:16, 19:47, 20:18, 20:49, 20:58.
No gaps.

Failures in the log are all transient or already self-resolved. No action needed:

| Failure | Window | Outcome |
|---|---|---|
| GH005 "refs longer than 255 bytes" (`DIG-732-...`) | 2026-10-05 10:06–15:26 (9x) | Self-resolved 15:56:58 — the tool truncates long ref names |
| DNS `Could not resolve host: github.com` | 2026-10-05 13:47–14:21, 2026-10-06 15:06 | Transient network; retry succeeded |
| `gh auth git-credential get` failure | 2026-10-05 20:04 | Credential cache race |
| HTTP 408 | 2026-10-05 18:00 | Transient |

## 2. Repos with unpushed work — one real case

**`twelve-x` / `feat/DIG-540-level-author-horizon-and-shared-band` — not on the remote at all.**

- `git rev-parse @{u}` fails: no upstream. `git ls-remote --heads origin 'feat/DIG-540*'` returns nothing.
- 4 commits not in `origin/develop`, all dated 2026-10-05:
  - `ea7cc81` fix(levels): drive the shared-band grid off-tick and pin the bare edge (DIG-540)
  - `14ae9bb` DIG-632: state the holding period unconditionally in build_author_context
  - `85e7148` feat(level_author): state the holding period in the prompt (DIG-540)
  - `2ceb5f9` docs(levels): measure the shared plausible band and keep one constant (DIG-540)
- Working tree also has 29 dirty files.
- The snapshot loop has been pushing it to `refs/backup/chris/twelve-x/662098ad-feat_DIG-540-level-author-horizon-and-s/…`
  every 30 min since 2026-10-05 22:39, so the work is **not lost** — but it exists only as a backup
  ref, never as a real branch. Nobody can open a PR from it.

Secondary risk: the `digithings` main worktree logged `digithings [HEAD] dirty=38..41` repeatedly
between 2026-10-06 04:50 and 15:06 — a **detached HEAD with 38–41 uncommitted files**.

## 3. Stranded remote branches — 288 in `digithings`

Method (per `work-custodian`): `origin/*` branches excluding `develop`/`main`/`HEAD`/`backup`,
last commit older than 3 days (cutoff 2026-10-03), keep those with commits not in `origin/develop`,
subtract branches that have an open PR.

| Step | Count |
|---|---|
| `origin/*` older than 3 days | 327 |
| … with commits not in `develop` | 295 |
| … minus branches with an open PR | **288 stranded** |

Age: 145 last touched 2026-09, 65 in 2026-08, 60 in 2026-10.
`module/*` and `chore/sync-module-*` (e.g. `module/digibase` 12 commits) are intentional long-lived
integration branches — excluded, not stranded.

Largest stranded branches by unmerged commits:

| Branch | Commits | Last touched |
|---|---|---|
| `chore/rescue-4429-footer-pixel-local` | 148 | 2026-10-02 |
| `claude/digithings-web-ui-refactor` | 144 | 2026-10-01 |
| `claude/sdca-rsi-confluence-and-period-search` | 99 | |
| `chore/rescue-4804-gold-artifacts` | 91 | 2026-10-02 |
| `cursor/digiquant-web-finalize-d8c5` | 50 | 2026-10-02 |
| `cursor/digiquant-hero-slice-i-d8c5` | 49 | 2026-10-02 |
| `cursor/pipeline-digiquant-web-d8c5` | 41 | 2026-10-02 |
| `cursor/integrations-digiquant-web-d8c5` | 41 | 2026-10-02 |
| `cursor/dashboard-digiquant-web-d8c5` | 41 | 2026-10-02 |
| `task/4895-dqweb-3910-message` | 40 | 2026-10-02 |
| `cursor/digiquant-dashboard-skeleton-mocks-67ef` | 33 | 2026-10-01 |
| `claude/sdca-full-recalibration` | 31 | |
| `cursor/desk-atoms-digicon-6a5f` | 29 | 2026-10-02 |
| `feat/digichat-dev-interface` | 24 | 2026-09-29 |

Plus a `cursor/missing-test-coverage-*` cluster (6 branches, 7–10 commits each), `fix/4991-fanout-leg-isolation`
and `fix/dockerignore-occ-ticket-seed-scripts` (6 each), `feat/publish-digichat-on-release-tag` (6),
`release/v0.1.0` (1, 2026-09-29), and a long tail of 1-commit strays (`task/4929-digitrace-rename`,
`task/4947-digivoice-banner-v58`, `task/4931-digitrace-phase2-dual-export`, `task/4761-phase3-image-bake`,
`task/4625-pr-title-lint`, `task/4818-digivoice-pr1-dictation`, and many `cursor/*`).

**Pattern worth naming:** the `digiquant` dashboard / web-rebuild family (`d8c5`, `3d52`, epic clusters)
appears as 5+ separate abandoned rebuild attempts. That is a repeated restart, not 5 independent strands.

## 4. Done issues with no merged PR — 45 issues, 23 PRs

Scoping note: PRs in this company do not carry the issue key in the title (only 31 of 3053 merged PRs
mention `DIG-n` in the title). A blanket identifier cross-reference would flag ~700 done issues, almost
all of them correctly-done operational work with no code. So this check is scoped to done issues that
**cite a PR number**: 139 done issues do, and 45 of them point at a PR that never merged.

All 23 unmerged PRs are in `digithings-ai/digithings`. Split:

### 4a. Closed without merging (4 PRs, 17 commits) — reviewed, all deliberate

None of these head commits is in `origin/develop`, but in every case the work was intentionally
superseded and **the head branch still exists on the remote**, so nothing is lost:

| PR | Branch | Commits | Why closed |
|---|---|---|---|
| #5055 | `feat/cron-snapshot-backfill-trigger` | 3 | Superseded by DIG-678 (Cloudflare-native trigger); replacement #5106 still **open** |
| #5077 | `task/306-a-datatap-answer-check-script` | 8 | DIG-306 landed instead via merged #5204 |
| #5081 | `task/469-cron-kick-arg-allowlist` | 4 | Salvaged into DIG-678 per DIG-699; some commits on open #5084 |
| #5159 | `task/1210-occ-tickets-pii-minimisation` | 2 | Partly carried on open #5148 |

**Actionable:** DIG-678's salvage is not finished — its replacements (#5106, #5084) and #5148 are all
still open.

### 4b. Open and parked (19 PRs)

A done issue whose PR is still open means the review concluded but the merge never happened.

| PR | Head branch | Done issue(s) |
|---|---|---|
| #5047 | `feat/dig-183-fx-hub-staleness-tone` | DIG-193, DIG-669, DIG-670 |
| #5057 | `task/193-fx-pairs-levels-as-of` | DIG-360 |
| #5058 | `task/354-rates-theses-as-of` | DIG-419 |
| #5061 | `DIG-102-digichat-write-the-ticket…` | DIG-422, DIG-436, DIG-471, DIG-895 |
| #5064 | `feat/dig-57-l1-snapshot-generation-guard` | (DIG-318) |
| #5074 | `DIG-284-mcp-tool-brake` | DIG-875 |
| #5080 | `task/462-digiquant-balance-path-sharpe-and-drawdown` | DIG-614 |
| #5106 | `feat/cf-native-snapshot-backfill-trigger` | DIG-765, DIG-973 |
| #5110 | `feat/dig-57-l2-consensus-generation-dedupe` | DIG-867, DIG-873 |
| #5126 | `task/5116-l1-----honest-rate-normalizer--stats-ser` | DIG-862 |
| #5142 | `task/1072-exa-digifetch-seam` | DIG-1114, DIG-1186, DIG-1209, DIG-1211, DIG-1212, DIG-1378 |
| #5144 | `task/1070-art9-registry` | DIG-1130 |
| #5147 | `task/509-1a-occ-grounding-slot` | DIG-1148 |
| #5148 | `task/1063-zammad-mask-by-default` (draft) | DIG-1412 |
| #5152 | `task/1139-digillm-egress-record` | DIG-1183, DIG-1373 |
| #5154 | `task/509-2a-no-fabricated-zero` | DIG-1190 |
| #5157 | `task/1194-vendor-terms-and-vendor-row` | DIG-1206, DIG-1418, DIG-1448, DIG-1477 |
| #5170 | `task/1184-egress-env-docs` | DIG-1373 |
| #5200 | `task/1318-vendor-terms-bloomberg-luxalgo` | DIG-1472 |

Repeat offenders: **#5142 (DIG-1072)** has 6 done review issues and is still open — it is blocked on
DCO `Signed-off-by` on 2 commits plus a stale base, and four separate issues were raised about the
sign-off gate not being in required checks. **#5061** has 4 done review issues and is still open.

## 5. Backups — the headline

Healthy:
- `dt-backup` config is correct: `EXCLUDE_NAMES=backups` is set, so the archive does not sweep up
  itself. `KEEP_DAYS=14`, `KEEP_DAYS_REMOTE=90`, `REMOTE_DEST=…/ProtonDrive…/digithings-backup`,
  cipher `aes-256-cbc`.
- Last backup `2026-10-06 03:17` — about 18 h old, inside the daily window. Next due 2026-10-07 03:17.
- **Off-Mac copy verified**: `dt-backup-20261006-031700.tar.gz.enc`, 474,466,560 bytes, present in the
  ProtonDrive folder with identical size and timestamp.
  Caveat: only the `.enc` is copied, not the `.sha256`, and the script itself says the upload cannot be
  programmatically verified (Proton FileProvider) — it logs "upload pending" only. Size+timestamp match
  is the strongest evidence available without decrypting.

Problem — **disk at 84%**:
- `/System/Volumes/Data`: 926 GiB total, 749 GiB used, **152 GiB free, 84% capacity**.
- Archive size tripled in three days: 35 M (Oct 4) → 140 M (Oct 5) → 465 M (Oct 6).
- Root cause is **not** self-inclusion. It is the Paperclip database dump:
  `~/.paperclip/instances/default/data/backups` holds **15 GB across 69 hourly dumps**, each ~446–448 MB,
  while the Oct 3 dumps were ~137 KB.
- Growth per day: Oct 3 = 2 dumps / 284 K; Oct 4 = 23 / 608 M; Oct 5 = 22 / 4.9 G; Oct 6 = 22 / 9.1 G
  in the first 21 h. That is roughly **10 GB/day and accelerating**.
- `dt-backup` embeds the newest dump, so the archive tracks the database size.
- `KEEP_DAYS=14` prunes only `dt-backup`'s own archives. **Nothing prunes Paperclip's dump directory.**

I did not delete anything: 15 GB is destructive, and the dump directory belongs to Paperclip (IT), not
to DevOps. This needs an owner decision.

## 6. Decisions requested

1. **Branch hygiene (CTO/EM).** 288 stranded branches is past the point of ad-hoc rescue. Decide a policy:
   bulk-delete the 1-commit strays, require a PR or an explicit discard for the large ones, and set a
   branch-age limit in CI.
2. **Branch pushes (CTO).** `twelve-x` `feat/DIG-540-…` exists only as a backup ref, and the `digithings`
   main worktree sat on a detached HEAD with 38–41 dirty files. `work-custodian` limits me to writing
   backup refs — it forbids me creating real branches — so I need someone authorised to push.
3. **Disk (IT).** Prune or compress `~/.paperclip/instances/default/data/backups`, and give Paperclip's
   own dump retention a policy. At the current rate the data volume is at risk well before the next
   hardware cycle.
4. **DIG-678 salvage (EM).** Finish the salvage of #5055/#5081 onto the replacement PRs.