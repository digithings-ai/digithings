# Develop sync + new-cascade adoption (Plan 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebase the gold branch onto current develop, adopt the #4794 PR3 supabase→R2 macro cascade (replacing our FRED-API/fredgraph assumptions), probe + re-add GVZCLS/NFCI/DTWEXBGS availability, rewrite the depth handoff to the R2 path, and adopt the #4828 honesty envelope in gate reporting — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Architecture:** Take develop's rewrite, don't fight it. `export_sdca_macro.py` is now supabase → `rows_from_r2` (sealed `fred__*` parquet); FRED-API/fredgraph helpers are deleted on develop, as are `fetch_fred_series`/`fetch_fred`. Our SERIES_FILES extension is re-applied onto their file (minus DTWEXBGS, which they skip by design). The dxy=0.5 seed vote is PRESERVED (local CSV + loader unchanged) while DXY re-staging gets its own probe — weights never change silently in this plan. Honesty-envelope functions (`stats/honesty.py`) are consumed as-is, no adaptation.

**Tech Stack:** Python, Polars, Pydantic v2, pytest (`-m unit`), ruff (line length 100), git worktree rebase discipline. Live `econ_series` probes are research actions (anonymous, no cookie) — allowed ONLY in Task 2's probe step with output recorded; tests stay offline as always.

**Spec:** Assessment 2026-09-30 (same session): #4794 PR3 removed `fetch_fred_series`/`fetch_fred` (kept row-mapper + Manifest types + Yahoo-FX), rewrote `export_sdca_macro.py` (+`rows_from_r2`, −fred helpers, −DTWEXBGS from SERIES_FILES), dropped 8 manifest series incl. GVZCLS/NFCI ("do not re-add without a probe"), cut macro_liquidity defaults to M2SL+UNRATE; #4828 added `stats/honesty.py` (`wilson`, `honest_rate`, `format_honest_rate`, guards) wired to tearsheets (schema 1.4); SDCA engine has ZERO commits since our base (catalog/optimize/walk-forward/settings clean); collisions confined to export script + its test + ARCHITECTURE.md + tearsheet files.

## Global Constraints

- Research-only: no `settings.json`, no `presets.json`, no `--push-supabase`, no workflow edits (except NONE in this plan — no new workflows).
- No silent vote changes: dxy stays 0.5, all other weights untouched. If DXY proves unstaged-unstageable, that becomes an owner checklist item, not an implementer edit.
- No live calls in tests, ever. The single live probe (Task 2) records raw output to the report; its result (not its data) is what later steps consume.
- R2/Supabase creds are unset here — anything needing them is procedure + verification, never faked.
- ruff line length 100 on touched files only (broad drift pre-existing — stash-prove if flagged). Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.

---

### Task 0: Rebase + conflict resolution

**Files:** Whatever conflicts (expected: `digiquant/scripts/export_sdca_macro.py`, `tests/dq/test_export_sdca_macro.py`, possibly `digiquant/ARCHITECTURE.md`, tearsheet files). Untracked staging (CSVs, `.scratch/`) stays out of the way.

**Interfaces:**
- Consumes: origin/develop HEAD.
- Produces: rebased branch, conflicts resolved per the rules below, green baseline.

- [ ] **Step 1: Fetch + rebase**

```bash
git fetch origin
git rebase origin/develop
```

Expected: conflicts in the predicted files (export script certain; test file certain; ARCH/tearsheets possible). If the rebase is clean (unexpected), skip to Step 3 and say so.

- [ ] **Step 2: Resolve per these rules (no deviations without NEEDS_CONTEXT)**

1. `export_sdca_macro.py`: take THEIRS (develop's rewrite) in full, then re-apply OUR delta on top: SERIES_FILES gains GVZCLS, WALCL, BAMLH0A0HYM2, BAMLC0A0CM, T5YIE, NFCI (NOT DTWEXBGS — they skip it by design; record the omission in the report). If their file has a different extension point (e.g. a registry instead of a dict), STOP with NEEDS_CONTEXT quoting their structure.
2. `tests/dq/test_export_sdca_macro.py`: take THEIRS as the base, then re-apply OUR pin test updated to the new SERIES_FILES (6 additions, no DTWEXBGS) + keep OUR GVZCLS staging test ONLY if `export_series`'s signature is unchanged (if changed, rewrite the test to the new signature — still offline, monkeypatched seams only).
3. Any test referencing `rows_from_fred_api`, `rows_from_fredgraph`, `fetch_fred_series`, or `fetch_fred` (ours or theirs): those functions are deleted on develop — delete or rewrite the referencing tests to the supabase→R2 cascade (offline seams: monkeypatch `rows_from_supabase` / `rows_from_r2`). List every such test in the report.
4. `macro_liquidity.py` defaults change (M2SL+UNRATE): our code does not consume it (verify with `grep -rn "macro_liquidity\|DEFAULT_MACRO_SPECS" digiquant/scripts/run_gold_* digiquant/src/digiquant/strategies/sdca/`) — confirm no-op in the report, touch nothing.
5. ARCHITECTURE.md / tearsheet hunks: take the semantically-correct side per hunk (develop's #4794/#4828 text wins on macro/honesty passages; ours wins on gold-leg rows); never delete the other's rows. If a hunk mixes both inseparably, STOP with NEEDS_CONTEXT quoting it.

- [ ] **Step 3: Baseline green**

Run: `.venv/bin/python -m pytest tests/dq/test_export_sdca_macro.py tests/dq/strategies/sdca/ tests/dq/data/test_enrichment_snapshots.py tests/dq/data/test_gold_enrichment_pulls.py -m unit -q`
Expected: PASS. Plus `ruff check` + `ruff format --check` on exactly the conflict-resolved files.
Expected: clean (stash-prove any broad-scope flag before touching unrelated files).

- [ ] **Step 4: Report (no commit — rebase replays existing commits; resolution is part of the replay)**

Report: per-file resolution (theirs/ours/merged + rule number), Step-2 item-4 grep outcome, baseline results, new HEAD + `git log --oneline -3`. If any NEEDS_CONTEXT triggered, the specifics go in the final message itself.

---

### Task 1: Cascade migration for our scripts + tests

**Files:**
- Modify: `digiquant/scripts/verify_macro_depth.py` + `tests/dq/test_verify_macro_depth.py` (only if they reference the deleted cascade — check first)
- Modify: `digiquant/scripts/pull_gold_enrichment.py` — NO (econ_series path unchanged; verify only).
- Modify: `digiquant/.scratch/gold_depth_handoff.md` — NO (Task 3 rewrites it; leave stale, note it).

**Interfaces:**
- Consumes: rebased tree from Task 0.
- Produces: zero references to deleted functions across our files; green suite.

- [ ] **Step 1: Find all references to the deleted cascade**

Run: `grep -rn "fetch_fred_series\|fetch_fred\b\|rows_from_fred_api\|rows_from_fredgraph\|FRED_GRAPH_CSV\|FRED_API_KEY" digiquant/scripts/ tests/dq/ digiquant/src/digiquant/strategies/sdca/ docs/superpowers/plans/2026-09-30-gold-*.md 2>/dev/null | grep -v ".pyc"`
Expected: a definitive list. Plan files (docs) are historical — DO NOT edit them (record hits as "historical, left intact"). For each LIVE code/test hit, Step 2 assigns: rewrite to supabase→R2 seams, or delete if dead.

- [ ] **Step 2: Rewrite or delete (code + tests only)**

Rules: `rows_from_fred_api(` calls → drop the tier (supabase → `rows_from_r2` chain per the rebased script); `rows_from_fredgraph(` fallbacks → same; `FRED_API_KEY` reads in our scripts → remove (key off the live path; record removal); tests pinning the old cascade → rewrite to monkeypatch `rows_from_supabase`/`rows_from_r2` (mirror the rebased test file's seams — read it first). TDD where behavior changes: failing test first. If a hit is inside a file Task 0 already resolved, say so and skip.

- [ ] **Step 3: Run + lint + commit**

Run: `.venv/bin/python -m pytest tests/dq/test_verify_macro_depth.py tests/dq/test_export_sdca_macro.py -m unit -v` + the broader Task-0 suite if any shared helper changed.
Expected: PASS. Ruff on touched files.
Expected: clean.

```bash
git add <touched files only>
git commit -m "Migrate gold scripts to supabase-R2 macro cascade (#4804)"
```

(If Step 1 finds zero live hits: report "no-op", no commit, proceed.)

---

### Task 2: Availability probes (GVZCLS / NFCI / DTWEXBGS) + manifest decision

**Files:**
- Create (untracked): `digiquant/.scratch/gold_manifest_probe.json`
- Modify (ONLY on probe-hit): `digiquant/src/digiquant/research/config/macro_series.yaml` (re-add entries in their original shape)
- Modify: `digiquant/.scratch/gold_depth_handoff.md` — NO (Task 3 owns it).

**Interfaces:**
- Consumes: anonymous `econ_series` (live, one-shot) + `rows_from_r2` readability (offline code check, no creds needed to read the function).
- Produces: probe verdicts + conditional manifest re-add. No staging runs here.

- [ ] **Step 1: Probe the three series (single live step, recorded)**

Run (one command, paste FULL output into the report):
```bash
PYTHONPATH=digiquant/src .venv/bin/python -c "
from digiquant.data.gloomberb.agent_tools import build_digifetch_tool_dispatcher
d = build_digifetch_tool_dispatcher()
import json
for sid in ['GVZCLS', 'NFCI', 'DTWEXBGS']:
    raw = d('digifetch_econ_series', {'series_id': sid, 'limit': 5, 'sort_order': 'desc'})
    doc = json.loads(raw)
    data = (doc.get('data') or {})
    obs = data.get('observations') or []
    print(sid, '->', 'HIT', len(obs), 'rows; first:', obs[0] if obs else None, '; keys:', sorted(data.keys()) if isinstance(data, dict) else type(data))
"
```
Expected: per-series HIT (≥1 obs) or MISS (error envelope / empty) with the raw shape visible. Write the parsed verdicts to `digiquant/.scratch/gold_manifest_probe.json` (`{series: {status, rows, first_obs}}`). If the dispatcher itself errors (network/auth/shape drift), STOP with NEEDS_CONTEXT (exact error) — do not retry with different params more than once, do not fall back to other tools.

- [ ] **Step 2: Conditional manifest re-add (hits only, original shape)**

For each HIT series: re-add its manifest entry EXACTLY as #4794 removed it (retrieve the original block with `git show 00dfc4b6c^:digiquant/src/digiquant/research/config/macro_series.yaml | grep -B2 -A4 "<ID>"` — same id/title/unit/cadence lines, no edits, no new series). MISS series: no manifest change; record the miss + consequence (GVZ/NFCI miss → their staged CSVs are frozen snapshots with no refresh path → owner decision; DTWEXBGS miss → DXY leg has no refresh path → owner decision per the Global Constraints). Commit ONLY if at least one entry is re-added:
```bash
git add digiquant/src/digiquant/research/config/macro_series.yaml
git commit -m "Re-add probed macro series to manifest (#4804)"
```

- [ ] **Step 3: R2-seal expectation note (report section, no action)**

Record: re-added series re-enter the cron's `--macro-manifest` universe → next cron seals `fred__<id>` generations (verify the cron reads this manifest path — cite the workflow/refresh arg default; if it reads a DIFFERENT manifest, flag it as a follow-up, do not edit the cron). No live cron trigger from this task.

---

### Task 3: Depth handoff rewrite (R2 path) + re-attempt protocol

**Files:**
- Modify: `digiquant/.scratch/gold_depth_handoff.md` (untracked — rewrite in place)
- Modify: `digiquant/scripts/verify_macro_depth.py` + test (ONLY if the cascade migration changed staging semantics — e.g. source labels; check first, else skip with a note)

**Interfaces:**
- Consumes: Task-2 probe verdicts; rebased `export_series` cascade (supabase → R2).
- Produces: a handoff that is executable where creds exist, with a self-test runnable HERE.

- [ ] **Step 1: Rewrite the handoff note**

Replace `gold_depth_handoff.md` contents with: (a) why the FRED-API version is dead (#4794, one line + commit); (b) the new re-stage commands
```bash
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/export_sdca_macro.py --cache-dir digiquant/data/price-history --series BAMLH0A0HYM2,BAMLC0A0CM
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/verify_macro_depth.py; echo "exit=$?"
```
(c) env required (`R2_*` for the R2 tier and/or Supabase creds for the first-hit tier — quote the exact variable names from the rebased script/reader, verified by reading, not memory); (d) expected post-fix bounds (BAML ~1996-12-31, ~7500 rows, exit 0); (e) the standing gap JSON (re-paste current); (f) the Task-1 duel re-confirmation trigger + gate follow-up trigger (exit 0 → re-run duel, then Task-3-class gate with hy/ig at the duel winner's weight — a NEW plan, not this one).

- [ ] **Step 2: Attempt the re-stage HERE (expect graceful failure, record it)**

Run the Step-1 re-stage command HERE. Expected outcome: supabase tier skipped (no creds) → R2 tier skipped/fails (no creds) → command exits non-zero or reports no observations. Record the EXACT failure mode in the report + append it to the handoff note (proves the handoff's env section is accurate). If it unexpectedly SUCCEEDS (creds present?), run the verifier immediately: exit 0 → re-stage lane is open (report it, do not expand scope); exit 1 with fewer gaps → report the new gap set. Under NO circumstances present fredgraph-tier output as full-depth.

- [ ] **Step 3: Report (no commit — handoff note is untracked; report carries the procedure)**

Report: failure-mode confirmation (or success), verifier-test status (unchanged/passing), handoff-note path. If Step-1's script needed verifier edits, they go through the normal test+lint+commit sub-steps (message `Adapt depth verifier to R2 cascade (#4804)`).

---

### Task 4: Honesty-envelope adoption in gate reporting

**Files:**
- Modify: TBD by inspection (candidate: `run_gold_curve_search.py` JSON writer and/or `build_gold_diagnostic_tearsheet.py` win-rate lines and/or the packet's fold table — packet is untracked, code changes only where counts exist).
- Tests: extend the nearest offline test file for whatever is wired (or none if the adoption is formatting-only inside an existing tested path — justify in the report).

**Interfaces:**
- Consumes: `digiquant.stats.honesty` (`wilson`, `honest_rate`, `format_honest_rate` — read the module first, use exact names).
- Produces: fold/report win-rates quoted with n + 95% CI wherever win counts exist; thresholds on CI lower bounds where thresholds exist.

- [ ] **Step 1: Inspect what win counts exist (read-only, then decide)**

Grep the v2 gate JSONs for win/count fields (`wins`, `num_trades`, `win_rate`) and the tearsheet builder for win-rate computation sites. Two branches, decided by evidence:
A. Counts exist (gate JSON or builder computes k/n): wire `format_honest_rate(k, n)` into the emitted JSON/packet-adjacent output + add/extend an offline test asserting the formatted string for a canned (k, n) (e.g. k=2, n=3 → exact expected string computed by hand from the wilson formula — read `honesty.py` first, do the arithmetic in the report).
B. No counts exist anywhere in gold outputs: report "no adoption surface", wire ONE honest line into the next-gate-runner path is OUT (no gate runs in this task) — instead add `format_honest_rate` usage to the duel/expansion report print (a real k/n exists? only if trials counted — if none, go with B-clean: no code change, report why, close the task with no commit).

- [ ] **Step 2: Implement the decided branch (A or B-clean)**

A: minimal edit (import + format call at the emission site), offline test with the hand-computed string, ruff, commit `Adopt honesty envelope in gold reporting (#4804)`. B-clean: report section only, no commit. Do NOT invent counts, do NOT rerun gates to manufacture k/n, do NOT touch tearsheet schema versions.

---

### Task 5: Full verification + cascade docs

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (macro-cascade passages: align our gold rows with the supabase→R2 truth; fix any FRED-API/fredgraph prose our plans added — grep ours first)
- Modify: `digiquant/data/enrichment/README.md` — NO (econ path untouched by #4794; verify with grep, leave alone).
- Verify: unit selection + ruff + `git status`.

**Interfaces:**
- Consumes: Tasks 0–4.
- Produces: docs matching the adopted cascade; evidence log.

- [ ] **Step 1: Update cascade prose**

Grep ARCHITECTURE.md for `fredgraph`, `FRED_API_KEY`, `rows_from_fred`, and our `(#4804)` macro rows. Update ONLY passages that describe the removed cascade or our FRED-based staging (supabase→R2 truth, `rows_from_r2`, DTWEXBGS-skipped + manifest-drop notes with the probe outcome from Task 2). Touch nothing else. If a passage is develop's (not ours) and already correct, leave it.

- [ ] **Step 2: Full verification pass**

```bash
.venv/bin/python -m pytest tests/dq/test_export_sdca_macro.py tests/dq/test_verify_macro_depth.py tests/dq/strategies/sdca/ tests/dq/data/test_enrichment_snapshots.py tests/dq/data/test_gold_enrichment_pulls.py -m unit -q
ruff check digiquant/scripts/export_sdca_macro.py digiquant/scripts/verify_macro_depth.py tests/dq/test_export_sdca_macro.py tests/dq/test_verify_macro_depth.py
ruff format --check <same file list>
git status --short
```

Expected: all green (stash-prove any failure as pre-existing before deciding); `git status` shows plan commits + `??` staging only; no committable data (check-ignore + extend ignores rather than committing data if violated).

- [ ] **Step 3: Commit docs + evidence log**

```bash
git add digiquant/ARCHITECTURE.md
git commit -m "Align gold docs with supabase-R2 macro cascade (#4804)"
```

Report final section: `git log --oneline` (plan commits), probe verdicts table, handoff path + status, honesty adoption outcome, DXY-leg staging status (the open owner item), deferred list for strategy work.

---

## Out of scope (not this plan)

- Grid/gate/fold/objective/weight changes of any kind — strategy work resumes AFTER this sync (fold-1 attribution, sensitivity evidence, inversion experiments).
- Credentialed execution (BAML re-stage, live snapshot backfill) — procedures + verifiers only; execution where creds exist.
- Manifest additions beyond Task-2 hits (no new series proposals).
- Promotion, nightly jobs, workflow edits, settings/presets/push.

## Self-review

1. Spec coverage: rebase+conflicts → Task 0 (per-file rules with STOP branches); dead-cascade purge → Task 1 (grep-defined list, docs excluded); probes + conditional re-add → Task 2 (single live step, original-shape rule, miss consequences); handoff rewrite + here-attempt → Task 3 (exact commands, env quoted from code, no fredgraph-as-full-depth); honesty adoption → Task 4 (inspect-first branch with hand-computed test string); docs+verify → Task 5. The DXY open item is carried explicitly (vote preserved + probe + owner checklist), not dropped.
2. Placeholder scan: commands, file paths, commit messages, test seams, and branch conditions are literal. STOPS name their trigger + required content. Task-4's A/B-clean branch is evidence-decided with defined actions each way.
3. Type consistency: `rows_from_r2` / `rows_from_supabase` seam names match the assessment-held rebased script; `wilson`/`honest_rate`/`format_honest_rate` match the assessment-held `stats/honesty.py`; probe ids (`GVZCLS`, `NFCI`, `DTWEXBGS`) identical in Task 2 steps; `gold_depth_handoff.md` / `gold_manifest_probe.json` paths identical across Tasks 2–3–5.
