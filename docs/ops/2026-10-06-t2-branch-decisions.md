---
title: T2 stranded branch decisions (DIG-1580)
date: 2026-10-06
owner: EM
policy: docs/ops/branch-hygiene-policy.md
---

# T2 stranded branch decisions

Owner decision record for every branch in the `T2-decide` tier of
`docs/ops/2026-10-06-stranded-branch-triage.tsv`, made under section 3 and
section 4 of the [branch hygiene policy](branch-hygiene-policy.md) (DIG-1561).
47 branches: **40 discard, 5 ship, 1 excluded, 1 deferred**.

Decision date: 2026-10-06. `develop` at decision time: `24c5f8c4`.
Deletion preconditions checked before any head was removed:

| Policy precondition | Status on 2026-10-06 |
| --- | --- |
| 4.1 Snapshot green | `dt-snapshot ledger` reports `Ledger OK`; `dt-snapshot check .` holds the main checkout (`LOCKED`, 42 uncommitted changes, 0 unpushed commits) |
| 4.2 No open PR | Confirmed per branch; the one branch with an open PR (#4965) is excluded, not deleted |
| 4.3 Tier evidence recorded | This document, posted in full on DIG-1580 |
| 4.4 Not excluded | Section 5 exclusions removed 1 branch (`module/digibase`) |
| 4.5 Archive ref before delete | Every one of the 40 discards was pushed to `refs/archive/<branch>` before the head was deleted |

## Three findings that changed the analysis

### 1. The triage TSV does not have the columns the issue named

DIG-1580 asked for `unmerged_patches`, `already_in_develop_patches` and
`artifact_content` in `docs/ops/2026-10-06-stranded-branch-triage.tsv`. No such
version exists in any revision (`git log --all -S'artifact_content'` over the
whole history). The file has 8 columns on all 295 rows:
`branch`, `last_commit_date`, `commits_not_in_develop`, `pr_state`,
`pr_number`, `verdict`, `tier`, `family`. The three missing columns were
re-derived from git for all 47 rows. The issue's group hints were also wrong:
`sdca` holds **2** T2 branches, not 15, and the `kaios/3d52` cluster holds
**4**, not 25.

### 2. `git cherry` is not squash-invariant, so the tier counts are inflated

Section 2 of the policy names `git cherry origin/develop origin/<branch>` as
the normative measure of unmerged work and claims patch-id invariance to
squash. That claim is wrong. A squash merge collapses N commits into one commit
whose patch-id is the combined diff, so the individual commit patch-ids can
never match anything on develop.

Worked example — `task/4311-gitleaks-env-example-gap`: PR #4320 merged
2026-09-17 as a single-parent squash commit `891eba9a5`, which **is** an
ancestor of `develop`. `git cherry` still reports all 3 commits as unmerged.
Its 3-dot diff touches 4 files, and each differs from develop only because
develop has since moved past the contribution.

Consequence: all 32 T2 branches whose PR merge commit is an ancestor of
`develop` are already-shipped work, not stranded work. They are leftovers of
`delete_branch_on_merge: false`, which section 6 already names as the biggest
prevention lever. The "184 recoverable patches" figure for T2 is inflated; the
real recoverable T2 content is the SDCA subsystem, not 184 patches.

### 3. The ADR the MCP branch wanted to add is already taken

`claude/mcp-tool-source-naming-migration` adds `docs/adr/0030-*` and renames
`digifetch_*` MCP tools to `gloomberb_*`. Develop already has
`docs/adr/0030-swappable-digiquant-stage-modules.md`, and develop already uses
`gloomberb_*` throughout `digiquant/`. Shipping that branch as written would
collide on the ADR number and re-apply a rename that already landed by
another route.

## Decisions

`Arch` is the archive ref, written as `refs/archive/<branch>`.

### Group A — 32 discard, PR merged to develop (precondition 4.1-4.5 met)

Every merge commit below is a single-parent squash that is an ancestor of
`develop`. The contribution shipped; the ref is a leftover.

| # | Branch | PR | Patches | Decision | Destination |
| --- | --- | --- | --- | --- | --- |
| 1 | `cursor/stripe-three-tiers-3d52` | 3412 | 8 | Discard | `refs/archive/cursor/stripe-three-tiers-3d52` |
| 2 | `task/3523-npm-audit-cloudflare` | 4383 | 3 | Discard | `refs/archive/task/3523-npm-audit-cloudflare` |
| 3 | `cursor/fx-hub-invite-auto-redeem-6527` | 3429 | 3 | Discard | `refs/archive/cursor/fx-hub-invite-auto-redeem-6527` |
| 4 | `task/4443-dashboard-performance` | 4453 | 7 | Discard | `refs/archive/task/4443-dashboard-performance` |
| 5 | `cursor/digiquant-dashboard-digichat-desk-3662` | 3664 | 6 | Discard | `refs/archive/cursor/digiquant-dashboard-digichat-desk-3662` |
| 6 | `cursor/digiquant-runner-phase1-3fd9` | 4789 | 6 | Discard | `refs/archive/cursor/digiquant-runner-phase1-3fd9` |
| 7 | `cursor/footer-pixel-wordmark-9da1` | 4898 | 5 | Discard | `refs/archive/cursor/footer-pixel-wordmark-9da1` |
| 8 | `chore/olympus-schedule-retry-3d52` | 3395 | 3 | Discard | `refs/archive/chore/olympus-schedule-retry-3d52` |
| 9 | `cursor/digiquant-ci-only-3660` | 3667 | 5 | Discard | `refs/archive/cursor/digiquant-ci-only-3660` |
| 10 | `cursor/digivoice-banner-esc-discard-379b` | 4937 | 4 | Discard | `refs/archive/cursor/digivoice-banner-esc-discard-379b` |
| 11 | `cursor/olympus-settings-pages-3d52` | 3251 | 4 | Discard | `refs/archive/cursor/olympus-settings-pages-3d52` |
| 12 | `feat/drop-olympus-public-path-dbc9` | 3320 | 3 | Discard | `refs/archive/feat/drop-olympus-public-path-dbc9` |
| 13 | `feat/fx-hub-nav-suppression` | 4032 | 3 | Discard | `refs/archive/feat/fx-hub-nav-suppression` |
| 14 | `task/1196-extract-fakesupabaseclient--parametrize-` | 3158 | 4 | Discard | `refs/archive/task/1196-extract-fakesupabaseclient--parametrize-` |
| 15 | `task/4204-gloomberb-refine` | 4213 | 4 | Discard | `refs/archive/task/4204-gloomberb-refine` |
| 16 | `task/4311-gitleaks-env-example-gap` | 4320 | 3 | Discard | `refs/archive/task/4311-gitleaks-env-example-gap` |
| 17 | `task/4430-q1-digiquant-rebuild` | 4441 | 4 | Discard | `refs/archive/task/4430-q1-digiquant-rebuild` |
| 18 | `task/4929-digitrace-rename` | 4936 | 4 | Discard | `refs/archive/task/4929-digitrace-rename` |
| 19 | `docs/sync-billing-house-llm-3670-3674` | 3678 | 4 | Discard | `refs/archive/docs/sync-billing-house-llm-3670-3674` |
| 20 | `task/4069-gloomberb-implementation` | 4085 | 4 | Discard | `refs/archive/task/4069-gloomberb-implementation` |
| 21 | `task/4429-digithings-rebuild-r2` | 4470 | 4 | Discard | `refs/archive/task/4429-digithings-rebuild-r2` |
| 22 | `task/4443-dashboard-recharts-retirement` | 4454 | 4 | Discard | `refs/archive/task/4443-dashboard-recharts-retirement` |
| 23 | `chore/gha-strict-essentials-2026-10-01` | 4919 | 3 | Discard | `refs/archive/chore/gha-strict-essentials-2026-10-01` |
| 24 | `cursor/digiquant-runner-phase2-9fb8` | 4812 | 3 | Discard | `refs/archive/cursor/digiquant-runner-phase2-9fb8` |
| 25 | `cursor/pause-digiquant-pipeline-clocks-6642` | 4917 | 3 | Discard | `refs/archive/cursor/pause-digiquant-pipeline-clocks-6642` |
| 26 | `feat/fx-hub-tiered-invites-and-twelvex-sync` | 4029 | 3 | Discard | `refs/archive/feat/fx-hub-tiered-invites-and-twelvex-sync` |
| 27 | `task/4110-full-coverage-phase-4` | 4130 | 3 | Discard | `refs/archive/task/4110-full-coverage-phase-4` |
| 28 | `task/4146-digifetch-pipeline` | 4157 | 3 | Discard | `refs/archive/task/4146-digifetch-pipeline` |
| 29 | `task/4429-d1-digithings-rebuild` | 4440 | 3 | Discard | `refs/archive/task/4429-d1-digithings-rebuild` |
| 30 | `task/4552-digichat-provider-search` | 4553 | 3 | Discard | `refs/archive/task/4552-digichat-provider-search` |
| 31 | `task/4761-phase3-image-bake` | 4894 | 3 | Discard | `refs/archive/task/4761-phase3-image-bake` |
| 32 | `task/4982-docs-occ---update-tenant-json-examples-t` | 4983 | 3 | Discard | `refs/archive/task/4982-docs-occ---update-tenant-json-examples-t` |

### Group B — 2 discard, PR merged to main, never to develop

Both PRs used `main` as their base, and both merge commits are on `main`, not
on `develop`. The develop-side delta is main-line work plus review artifacts.

| # | Branch | PR | Patches | Decision | Destination |
| --- | --- | --- | --- | --- | --- |
| 33 | `fix/4991-fanout-leg-isolation` | 4992 | 4 | Discard | `refs/archive/fix/4991-fanout-leg-isolation` |
| 34 | `fix/dockerignore-occ-ticket-seed-scripts` | 4989 | 4 | Discard | `refs/archive/fix/dockerignore-occ-ticket-seed-scripts` |

Evidence for #33 and #34: the develop-side outcome is already present —
`tests/ds/test_multi_index_query.py` and `tests/ds/test_multilingual_embedder.py`
carry the fan-out coverage, `.dockerignore` carries
`!scripts/index_occ_tickets.py`, and develop's `b9934e0b0` dropped the
develop-only `[program:seed_occ_tickets]` boot step. The files the branches add
that develop lacks (`scripts/build_occ_tickets_seed.py`,
`apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl` and their
tests) are the #4987 carve that belongs to main's release line, and
`review-4989.md`, `review-4992.md`, `review-promote-occ-chat.md` are the
artifacts section 6 clause 5 says must not live on a branch.

The two overlap: `fix/4991-fanout-leg-isolation` contains
`fix/dockerignore-occ-ticket-seed-scripts`'s commit `2757a691`. Neither ships,
so no survivor is needed; if either is ever reopened, `fix/dockerignore-occ-ticket-seed-scripts`
is the more complete ref.

### Group C — 1 excluded, 1 deferred

| # | Branch | PR | Patches | Decision | Reason |
| --- | --- | --- | --- | --- | --- |
| 35 | `module/digibase` | 2174 | 3 | **Excluded, no action** | Policy section 5: `module/**` is ruleset-protected and must never be deleted. The TSV `verdict` column already says `long-lived-module-branch` |
| 36 | `task/4947-digivoice-banner-v58-gap` | 4965 | 4 | **Deferred to 2026-10-20** | PR #4965 is open. Policy section 5 and precondition 4.2: a branch with an open PR is not stranded. Real in-flight work — digivoice banner v5.8 (hug, drag/snap, hover controls) across 12 files |

### Group D — 6 discard, PR closed or absent

| # | Branch | PR | Patches | Decision | Destination | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| 37 | `cursor/dashboard-wireup-plan-e1fe` | 4975 | 5 | Discard | `refs/archive/cursor/dashboard-wireup-plan-e1fe` | Plan-only, 1 file. `docs/plans/2026-10-02-digiquant-dashboard-production-wireup.md` is absent from develop, but the dashboard it planned shipped through other merged branches. Superseded plan |
| 38 | `claude/mcp-tool-source-naming-migration` | 4560 | 4 | Discard | `refs/archive/claude/mcp-tool-source-naming-migration` | Supersedes #45 but its unique delta is dead: the `gloomberb_*` rename already landed on develop, and its `docs/adr/0030-*` collides with the existing `0030-swappable-digiquant-stage-modules.md`. Its live SDCA content is salvaged via #45 |
| 39 | `feat/digithings-web-secondary-pages-cards` | 4949 | 4 | Discard | `refs/archive/feat/digithings-web-secondary-pages-cards` | Strict subset of #40 — same four commits, minus the pipeline phase cards, strategy badges and scroll fix. #40 survives |
| 40 | `feat/rename-frontend-dashboard-dbc9` | 3297 | 3 | Discard | `refs/archive/feat/rename-frontend-dashboard-dbc9` | Renames `frontend/olympus` to `frontend/dashboard` across 551 files. `frontend/` no longer exists on develop at all; olympus was retired by `docs/adr/0026-retire-olympus-atlas-hermes-kairos.md`. The rename target is gone |
| 41 | `cursor/digiquant-dashboard-skeleton-plan-1a44` | 4908 | 3 | Discard | `refs/archive/cursor/digiquant-dashboard-skeleton-plan-1a44` | Plan-only, 1 file, absent from develop. Same group decision as #37 — superseded by the shipped dashboard |
| 42 | `cursor/kairos-human-gates-3d52` | 3267 | 3 | Discard | `refs/archive/cursor/kairos-human-gates-3d52` | Status bookkeeping only, 4 files under `docs/agent-backlog/kairos-tenancy/`. Kairos was retired by ADR 0026, and every added line is already present in develop's copies |

### Group E — 5 ship

| # | Branch | PR | Patches | Decision | Destination |
| --- | --- | --- | --- | --- | --- |
| 43 | `cursor/missing-test-coverage-4234` | 2802 | 4 | **Ship** | Leaf DIG-1580-1 (root tooling test coverage) |
| 44 | `cursor/missing-test-coverage-1e2d` | 3026 | 3 | **Ship (partial)** | Leaf DIG-1580-1 (root tooling test coverage) |
| 45 | `claude/sdca-develop-sync` | none | 3 | **Ship** | Leaf DIG-1580-2 (SDCA subsystem port). Survivor of the #38/#45 pair |
| 46 | `cursor/sdca-solo-then-combine-af6c` | 3282 | 6 | **Ship** | Leaf DIG-1580-3 (Stage 0 gate + Stage 1 blend ranking) |
| 47 | `cursor/digiquant-section-new-brand-dev-1a1c` | 4916 | 6 | **Ship** | Leaf DIG-1580-4 (digiquant.io rebrand UI). Survivor of the #39/#47 pair |

`claude/sdca-develop-sync` is the highest-value salvage in T2. Develop's SDCA
package is materially smaller than the branch's:

| File | On develop | On branch |
| --- | --- | --- |
| `sdca/indicator_catalog.py` | 18.2 kB, 17 top-level defs | 49.9 kB, 25 top-level defs |
| `sdca/price_oscillators.py` | 13.8 kB | 38.0 kB |
| `sdca/stage_a.py` | 7.0 kB | 17.3 kB |
| `sdca/curve_optimize.py` | 22.6 kB | 41.8 kB |
| `sdca/weight_search.py` | 7.6 kB | 15.9 kB |

It must be **ported, not merged raw**: its merge-base is over a thousand
commits behind develop, so the branch diff is +7084/-475 across 47 files of
research code.

## Overlap rulings

| Pair | Survivor | Discarded | Why |
| --- | --- | --- | --- |
| #39 `feat/digithings-web-secondary-pages-cards` / #47 `cursor/digiquant-section-new-brand-dev-1a1c` | #47 | #39 | #39 is a strict subset of #47's four commits |
| #38 `claude/mcp-tool-source-naming-migration` / #45 `claude/sdca-develop-sync` | #45 | #38 | #38 is the superset, but its extra content (the MCP rename and its ADR) already exists on develop. #45 holds the only live content |
| #33 `fix/4991-fanout-leg-isolation` / #34 `fix/dockerignore-occ-ticket-seed-scripts` | neither | both | Both shipped to main. #34 is the more complete ref if either is ever reopened |

## Follow-up leaves

Four leaves carry the five ship decisions. Each starts from failing tests and
is a port, not a branch merge.

| Leaf | Owner | Scope |
| --- | --- | --- |
| DIG-1580-1 | Backend 1 | Root tooling test coverage from #2802 + #3026. Retargets to develop's layout: `score.py` moved to `digidev/scripts/score.py`, `score_delta.py` was removed, so `tests/scripts/test_score_delta.py` is dropped and the rest is rebased |
| DIG-1580-2 | Quant | Port the SDCA research subsystem from `claude/sdca-develop-sync`. Failing tests first, then `indicator_catalog.py`, `price_oscillators.py`, `stage_a.py`, `curve_optimize.py`, `weight_search.py`. Any ADR goes in as 0031 or later, never 0030 |
| DIG-1580-3 | Quant | SDCA Stage 0 solo-indicator OOS gate and Stage 1 blend ranking from #3282. Sequenced after DIG-1580-2 because both rewrite the same `sdca/` package |
| DIG-1580-4 | Frontend | digiquant.io rebrand from #4916 — secondary page cards, pipeline phase cards, strategy badges, scroll glide, centred pixel wordmark |

## Census effect

T2 goes from 47 to **0**. Two caveats for the next census:

1. The 40 archive refs under `refs/archive/` hold the discarded work. They are
   not branches and do not appear on any branch list, but they are still refs.
2. The tier counts for T1 and T3 are inflated by the same squash artifact
   described in finding 2. Policy section 2 needs a companion measure that is
   squash-aware — merge-commit ancestry plus a residual-content check — before
   the next quarterly tier count is trusted.