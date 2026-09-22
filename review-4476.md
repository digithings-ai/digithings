# Review — PR #4476 (commit `40a0b8e5d`)

- **Reviewer role:** fresh-context read-only review subagent (not the author; no edit/commit access used beyond this file)
- **Subject:** PR #4476 — `chore(digiquant): complete W4 brand/docs cleanup (#4475)`, single commit `40a0b8e5d`, base `module/digiquant`, head `task/4475-w4-brand-docs-cleanup`, 256 files, +1245/−1239
- **Worktree:** `/Users/chrisstefan/Code/digithings/.worktrees/task/4475-w4-brand-docs-cleanup` (`git status` clean; `HEAD` == worktree)
- **Verdict:** **SAFE TO MERGE** — no functional, wire-contract, or test breakage found. All findings are cosmetic/prose or informational; the declared carve-outs and frozen contracts hold.
- **Severity counts:** HIGH 0 · MEDIUM 0 · LOW 5 · INFO 2

---

## Verified-clean (with evidence)

| Check | Result |
|---|---|
| `digiquant/supabase/migrations/**` | **0** changes |
| `apps/digiquant-web/**`, `packages/**` | **0** changes (out-of-scope, correctly untouched) |
| `openwiki/**`, `apps/digichat/cli/package-lock.json` | **0** changes (generated) |
| `docs/adr/**`, `docs/plans/**`, `docs/reviews/**`, `docs/superpowers/plans/**`, `docs/dashboard-audits/**` | **0** changes |
| Directory rename | 30 renames `kairos-tenancy/ → execution-tenancy/` (R100/R099/R098), **same inner filenames** (`K0`–`K5`, `T0`–`T5`, `kairos-cron-check.workflow.yml`, `pipeline-olympus-notify.env.yml`, …). No inner renames. |
| `kairos-tenancy` remaining hits | All carve-outs: frozen migrations (`096`, `128`, `cutover/113`, `cutover/900`), historical docs (`docs/superpowers/plans`, `docs/superpowers/specs`), the historical spec filename, and generated `openwiki/dashboard/architecture.md:81`. **No live path reference to the old directory remains.** |
| Historical spec filename | Not renamed — `docs/superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md` still present; moved-dir references use the kairos filename. |
| Frozen digisearch contracts | `digisearch/**` not in the diff at all; `RESEARCH_INDEX_NAME` / `DIGISEARCH_ATLAS_INDEX` = `"atlas"` untouched (`digisearch/src/digisearch/research_ingest.py:35`). |
| `_redirects` legacy atlas/hermes/kairos | `apps/digiquant-web/public/_redirects` — 0 changes. |
| `test_envcompat.py` `forbidden` guard | `tests/dq/dashboard/test_envcompat.py:27` still `("OLYMPUS_", "ATLAS_", "KAIROS_")`. Only the cron-file path changed, keeping the inner filename. |
| Three heading-level `H1` cases | `tests/scripts/docs_onboard/test_write_vault_notes.py:226`, `apps/dashboard/app/portfolio/performance/page.test.ts:8`, `apps/dashboard/lib/render-pipeline-payloads.test.ts:447` — **0 changes** each; content still `H1`. |
| "PM direction memo" / "PM direction" kept | Yes (e.g. `render-pipeline-payloads.ts`, `pm-rationale.ts`, `pm-direction-view.ts`). |
| No identifier renames | Diff scan for `H[1-9]_` / `_H[1-9]` / `h[1-9]_` found only prose (`phase_h1 → thesis` mapping text). |
| `phase` field (prompt_walk_inventory) | `PromptWalkNode.phase` read nowhere (`grep .phase` → only the file itself); test asserts only `structured_output`; `PROMPT_STRUCTURED_OUTPUT_WALK.md` has no phase column; no `A0/A1/A4` consumer remains. Display-only claim **holds**. |
| Old-string consumers | No remaining consumer of `H8 lineage validation failed`, `Risk-sizing (H8)`, `H6 deliberation failed` (repo-wide grep clean). |
| Lockstep assertion updates | `phase7e_risk_sizing.py` `notes`/log strings updated together with `tests/dq/portfolio/test_phase7e_risk_sizing.py:254,273,602,1193,1220,1242,1290`; commit error strings updated with `tests/dq/portfolio/test_commit_run.py:837`. |
| `config/model_modes.yaml` | Only a comment changed (`pin H6 deliberation` → `pin deliberation`). |
| JSON schema files | `pipeline_schedule.v1.json`, `pm-direction-memo.schema.json`, `shadow_criteria/v1.json` — **description/rationale prose only**, no `properties`/`required`/`enum`/`$id` changes. |
| `digigraph/src/digigraph/graph/pipeline_builder.py` | Docstring prose only. |
| Committed as edited | `git diff HEAD` for `tests/dq/portfolio/test_phase7e_risk_sizing.py` and `tests/dq/portfolio/test_commit_run.py` → empty. |

---

## Findings

### F1 — LOW — Incomplete `H1–H9` sweep: leftover step-marker `H6` in scope
`apps/dashboard/lib/render-pipeline-payloads.test.ts:398`
```ts
it('renders H6 PM↔analyst chat turns published under rounds (DBO shape)', () => {
```
This file is inside the declared extended scope (`apps/dashboard/**`) and carries a standalone step-marker `H6` (→ `deliberation`). The file was **not touched** by the commit (`git show --stat 40a0b8e5d -- <file>` = empty), so the sweep missed it. The scoped grep (c) therefore returns this hit alongside the three allowed `H1` cases. Cosmetic (test-title string, unasserted), but it is a genuine incomplete sweep per the task's own criterion.

### F2 — LOW — Incomplete dedup: compound doubled prose introduced by the sweep
The commit message claims a dedup pass collapsed doubled words. It caught adjacent doubles (the (d) regex is empty), but not the compound forms below. Every line is an **added** (`+`) line from `40a0b8e5d`:

- `digiquant/src/digiquant/research/testing/simulator.py:368` — `# analyst unified analyst` (was `# H5 unified analyst`)
- `apps/dashboard/lib/types.ts:495` — `* The analyst unified analyst output (` was `* The H5 unified analyst output (`)
- `tests/dq/research/test_pipeline_simulation.py:277` — `# analyst unified analyst: one call per ticker.`
- `tests/dq/research/test_phase67.py:653` — `# ─── analyst unified analyst tests ───`
- `tests/dq/portfolio/test_screener_focus_roster.py:1` — `"""screener opportunity screener — focus roster held invariant (#936)."""`
- `digiquant/ARCHITECTURE.md:2575` — `vehicle_map["vehicle_map thesis vehicle map"]`
- `digiquant/ARCHITECTURE.md:2576` — `screener["screener opportunity screener"]`
- `digiquant/ARCHITECTURE.md:2578` — `analyst["analyst asset analyst ×N"]`
- `digiquant/src/digiquant/portfolio/docs/ARCHITECTURE.md:625` — `analyst["analyst asset analyst ×N"]`
- `digiquant/src/digiquant/portfolio/templates/schemas/pm-direction-memo.schema.json:4` — `"direction portfolio direction artifact …"`
- `digiquant/src/digiquant/portfolio/phases/phase7e_risk_sizing.py:125` — `"""Map direction confidence to an sizing size multiplier in [0, 1].` (also `:118` `analyst/deliberation analyst context`)
- `apps/dashboard/lib/render-pipeline-payloads.ts:538` — `/** Markdown for a bull/bear debate summary or deliberation PM↔analyst deliberation. */`
- `digigraph/src/digigraph/graph/research_agent.py:245` — `(observed 31/39 deliberation deliberations on 2026-07-31)`

Prose-only; no runtime effect. Optional cleanup.

### F3 — LOW — Runtime-rendered markdown string changed (not just comments/test-labels)
`apps/dashboard/lib/render-pipeline-payloads.ts:670`
```diff
-    out.push('## H4 roster (read-only)', '', roster.map((t) => `- ${t}`).join('\n'), '');
+    out.push('## screener roster (read-only)', '', roster.map((t) => `- ${t}`).join('\n'), '');
```
This is a **runtime output string** (markdown heading emitted by `renderAttentionPlanMarkdown`, called from `render-document-from-payload.ts:70`), not a comment/test label. The task asked to confirm only comments/test-labels changed in this file, so it is flagged. **Assessed as harmless:** no consumer asserts either heading — repo-wide grep for `H4 roster` / `roster (read-only)` returns only this line, and `render-pipeline-payloads.test.ts:563` exercises `renderAttentionPlanMarkdown` on a payload without a roster (branch not hit). It is consistent with the H4→`screener` mapping.

### F4 — LOW — Inconsistent range substitution in schema description
`apps/dashboard/lib/settings/schemas/pipeline_schedule.v1.json:9`
```diff
-          "description": "Run portfolio deliberation (H1\u2013H9 intent) on this weekday.",
+          "description": "Run portfolio deliberation (thesis\u2013H9 intent) on this weekday.",
```
`H1` → `thesis` but `H9` was left, producing the half-migrated range `thesis–H9` (mapping says `H9 → commit`). Human-readable `description` only; nothing asserts it. Cosmetic inconsistency. (Note: this is why the scoped `\bH[1-9]\b` grep did not surface it — the file stores the en-dash as the literal escape `\u2013`, so `H9` is not word-bounded.)

### F5 — LOW — Declared carve-out letter vs. necessary link fix (`docs/superpowers/**`)
`docs/superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md` — 1 line modified:
```diff
-[`docs/agent-backlog/kairos-tenancy/`](../../agent-backlog/kairos-tenancy/README.md)
+[`docs/agent-backlog/execution-tenancy/`](../../agent-backlog/execution-tenancy/README.md)
```
The carve-out says "Historical docs must be untouched: … `docs/superpowers/**`". This is a literal breach of one line. However it is the **minimum necessary** change: the link target directory was renamed, and `make doc-check` scans this file (414 md files), so leaving it would turn `check_doc_links` red. The separate carve-out ("spec filename must NOT be renamed") is respected. Recommend the PR body explicitly name this one-line exception; otherwise no action needed.

### F6 — INFO — Residual step markers left outside the declared sweep scope
Not findings under the task's fixed path list, but recorded for completeness:
- `.github/workflows/pipeline-digiquant-allocation-shadow.yml:15`, `.github/workflows/pipeline-digiquant.yml:283,326`, `.github/digiquant-pipeline.yml:15` (H9/H4 markers; `.github/**` untouched by this PR)
- `scripts/validate_model_routing.py:144` — `portfolio/H6 phases` still present. **Inconsistency:** its test `tests/scripts/test_validate_model_routing.py` *was* swept (`per-ticker H6 deliberation slugs` → `per-ticker deliberation slugs`) while the source was not.
- `packages/ui/**` (`DESIGN.md`, `src/components/repo-activity/demo.ts:46`, `src/data/subsystems.ts:72`), `apps/digiquant-web/app/subsystems/[id]/page.tsx:23`, `openwiki/**` — deliberately out of scope / generated.

### F7 — INFO — `openwiki` stale link (expected)
`openwiki/dashboard/architecture.md:81` still points at `docs/agent-backlog/kairos-tenancy/PRICING.md`. `openwiki/**` is a generated carve-out (0 changes) and refreshes in CI, so this is expected, not a defect.

---

## Independent verification of PR claims (command outputs)

Run from the worktree.

```
$ /Users/chrisstefan/Code/digithings/.venv/bin/ruff check digiquant/src digigraph/src tests config apps/dashboard/lib
All checks passed!                                          # exit 0

$ /Users/chrisstefan/Code/digithings/.venv/bin/ruff format --check \
    digiquant/src/digiquant/research digiquant/src/digiquant/portfolio \
    digiquant/src/digiquant/dashboard/learning digiquant/src/digiquant/dashboard/replay/walk_forward.py \
    tests/dq/research tests/dq/portfolio tests/dq/learning \
    tests/dq/replay/test_walk_forward.py tests/dq/replay/phase4_e2e_fixtures.py tests/dq/replay/test_phase4_end_to_end.py
372 files already formatted                              # exit 0

$ python -m pytest tests/dq/portfolio/test_phase7e_risk_sizing.py tests/dq/portfolio/test_commit_run.py \
    tests/dq/portfolio/test_deliberation_amendment_wiring.py tests/dq/research/test_diagnostics.py \
    tests/dq/research/test_pipeline_simulation.py tests/dq/research/test_simulator_gates.py \
    tests/dq/research/test_digest_briefing.py tests/dg/test_digiquant_models.py \
    tests/scripts/test_validate_model_routing.py -m unit -q -p no:cacheprovider --timeout=180
311 passed, 1 deselected in 2.55s                         # exit 0

$ bash tests/scripts/test_create_pr_component_regex.sh
create_pr component regex: 8 passed, 0 failed             # exit 0

$ make doc-check
check_doc_links: OK (414 markdown files scanned)          # exit 0
```

All five match the PR body's claims exactly. `git status --porcelain` is empty; `git diff HEAD` for the two assertion-bearing test files is empty (files committed as edited).

## Unverified / out of scope
- I did not execute the TypeScript/Vitest suite (`apps/dashboard` tests) — the JS-side changes are comment/string only, and the one runtime string (F3) has no asserting test, but I did not run Vitest to confirm green.
- I did not review every one of the 256 files line-by-line; the sweep was validated structurally (scope carve-outs, wire-token scan, identifier scan, frozen contracts) plus the sampled semantic areas listed above.
