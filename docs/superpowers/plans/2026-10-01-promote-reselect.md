# Promote the reselected shape (Plan 17) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the reselected v6 shape promotable branch-side: sell-mask support in the live tearsheet path, nightly staging for the mask inputs, `gold_sdca` entry + preset + provenance updated to the reselected candidate (v3 superseded on-record, not erased), and PR #4893 text updated — merge and any Supabase push stay owner-side, on branch `task/4804-sdca-strategy-for-gold--gld`.

**Standing facts:** Reselected #1: mean OOS flat +24.32 / lump +3.85, feasible all folds (Rule-B), fresh sens STABLE 1.63; full-history diagnostic +279.1% vs lump +248.7. Disclosures (every artifact): selection-on-metric optimism; thin +3.85 margin + f2 lump −0.81 (1 mask day); f1 zero mask days; #2–#4 projection tie; holdout ABSENT (spent, never re-scored). v3 record (PROMOTE-CANDIDATE + holdout −21.16%) stays in scratch/packet history. Engine veto mechanism landed (backtest + Nautilus + curve_sim, None-default, BTC-parity proven).

**Candidate decision (pre-registered, owner-picked 2026-10-02):** `gold_sdca` entry moves to the reselected candidate (buy vote = v4 vote: rolling90/z1.0 + m2/uup 0.5 + osc 0.25; curve = reselected gated shape buy 35/60/c1.0 sell 65/30/c1.0 no-mids; mask = strict box z≤−2.0 & m≥1.5). v3 settings/preset/provenance REMAIN in the tree for history (do not delete); the entry + provenance notes record the supersession with reasons (beats-both vs v3's flat-only + holdout trail) and the thin-margin caveat.

**Architecture:** Three shared-path extensions, all default-preserving: (1) `generate_tearsheets.py` SDCA branch builds the sell mask from staged series + entry box levels and threads `sell_dates` into the strategy/backtest (BTC entries carry no mask spec → None → byte-identical); (2) settings entry gains an optional `sell_mask` block (`box_z`, `box_mayer`, series refs — read the entry schema first, extend don't reshape); (3) nightly workflow gains a DFII10 staging step (mirror the T5YIE/M2SL pattern read-first; mayer needs no step — GLD closes already staged). Mask builder reused from `build_gold_sell_mask.py` (import, don't duplicate).

## Global Constraints

- Research-only except the three shared-path extensions (all additive/optional, BTC-safe by unmodified-green suites, not asserted). No live-trading paths, no `--push-supabase` from anywhere (no creds here anyway), no merge (PR edit only via `gh pr edit`, never `gh pr merge`).
- BTC parity hard gate: every pre-existing BTC/engine/Nautilus/generate test passes UNMODIFIED. Any red = STOP.
- No pandas, pydantic v2, ruff 100 on touched files. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.
- Frozen: reselect shape/weights/box, v4 buy vote, gate numbers (quoted, never recomputed). No gate/seed re-runs, no holdout contact, no threshold/space tuning.
- Standing owner rules: every iteration ships visuals (Task 5); temp preview edits stay uncommitted with REVERT-BEFORE-MERGE markers.

---

### Task 1: Live-path mask support (generate + strategy wiring + tests)

**Files:**
- Modify: `digiquant/scripts/generate_tearsheets.py` (SDCA branch: read entry `sell_mask` block; build mask via the SHIPPED builder, not a copy; thread `sell_dates` into materialization + strategy overrides + provenance mask-day count — read the Plan-11-generalized sites first, nothing else touched)
- Modify: settings-entry schema site(s) for the `sell_mask` block (grep `gold_sdca` + `risk_model` across src — extend, don't reshape; BTC entries gain nothing)
- Modify: nearest generate-tearsheets test home (grep first — extend, don't create): masked gold-shaped entry through the path with stubbed seams (mirror the Plan-11 test pattern); asserts: mask built from box levels (strict values), sell_dates reach the strategy, provenance names the mask, BTC entry resolves mask None
- Modify: NONE else (curve/composite/backtest/nautilus already carry the veto from Plan 15)

**Interfaces:**
- Consumes: `build_gold_sell_mask.py` builder; entry `sell_mask` block; staged DFII10 + GLD closes.
- Produces: mask-aware live path with BTC byte-identity. Tasks 2–4 consume it.

- [ ] **Step 1: Read-first (entry schema + Plan-11 sites + test home + builder import surface)**

Record verbatim: entry dict shape (where `risk_model`/`indicator_weights` live, how window/z reach the selector — the reselect needs rolling90/z1.0 through this path); the 4 Plan-11 sites' current text; the builder's importable function + its inputs; the test home's seam pattern. STOPs: entry schema can't carry an optional block cleanly (NEEDS_CONTEXT); builder not importable without engine imports (NEEDS_CONTEXT — don't copy math); window/z not threadable to the selector (NEEDS_CONTEXT — reselect rails depend on it).

- [ ] **Step 2: Failing tests first (gold mask through path, BTC None)**

Mirror-plan-11 pattern with stubbed rails/framework seams: mask dates reach strategy overrides; provenance mask-day count; BTC entry → mask None with identical outputs (paired assert). Expect FAIL (no block).

- [ ] **Step 3: Implement (three minimal edits, nothing else) + GREEN + lint + commits**

Suites: touched homes FULL + engine subset + presets/asset-profile `-m unit -q`, all UNMODIFIED-green except new tests. Ruff clean. Commits (one per edit + tests, messages per brief pattern with #4804).

## Ruling 1 (Plan 17): fail-closed mask required pre-Task-3 (issued after Task-1 review)

Task-1 review CONFIRMED fail-open: missing DFII10 → no `sell_dates` → veto None → sells proceed unmasked, violating the promoted premise ("sells only at secular extremes"). Severity HIGH for promotion. Required fix (Task 1b, test-first, same files): missing/unreadable DFII10 → `sell_dates` = EMPTY set (sells blocked — premise-preserving for a long-biased system) + provenance records an explicit `mask_unavailable` flag (never silent). Trigger condition is exact: the empty-set rule applies ONLY when a mask was specified but its inputs are missing; BTC/no-mask entries keep None as today. Companion LOW: provenance mask-day count must label its frame (full delayed frame vs trade window — one-line note fix, same edit). Both ride with Task-1b tests; Task 3 promotion is BLOCKED until this lands.

---

### Task 2: Nightly DFII10 staging step (additive workflow edit)

**Files:**
- Modify: `.github/workflows/pipeline-digiquant-tearsheets.yml` (ADD DFII10 fetch step mirroring the T5YIE/M2SL step — read the workflow first; additive-only hunk, zero modifications to existing steps or STOP)
- Create: pin test mirroring the Plan-11 staging-pin pattern (step presence, series/stem, no secrets, no existing-step modification; fail-first RED then GREEN)

**Interfaces:**
- Consumes: Task-1 mask path (needs fresh DFII10 beside GLD/UUP/M2SL at nightly).
- Produces: staged DFII10 at nightly. (Mayer stays GLD-derived; no step. Mask itself is built at generate time, not staged — state that.)

- [ ] **Step 1: Read workflow + pin test RED**
- [ ] **Step 2: Additive step + GREEN + lint + commit**

```bash
git add .github/workflows/pipeline-digiquant-tearsheets.yml <pin test>
git commit -m "Stage DFII10 for gold sell-mask at nightly (#4804)"
```

---

## Ruling 2 (Plan 17): series-support guard required pre-Task-3 (issued after Task-2 review)

Task-2 review found a MAJOR: post-develop-merge, the workflow (from develop) would invoke `--series DFII10` against a main-pinned export script without DFII10 support → exit 2, blocking the whole nightly run including BTC/Slapper. "Same-PR atomic merge" does not close the develop-vs-main skew. Required fix (Task 2b, same two files): guard the DFII10 step on script support (e.g. `grep -q '"DFII10"'` the export script or equivalent capability probe — read-first what the script offers; skip-with-warning when unsupported, never hard-fail), + pin-test coverage (guard present; skip path exercised). Task 3 promotion is BLOCKED until this lands; PR text must still carry the promotion-ordering note.

### Task 3: Promotion artifacts (entry + preset + provenance + packet + PR text)

**Files:**
- Modify: `settings.json` (gold_sdca entry → reselect: risk_model/weights/preset pointer/sell_mask block + supersession note naming v3 + thin-margin caveat — entry only, no other key touched)
- Modify: `presets.json` (NEW preset for the reselected shape — read how gold_optimized is stored; v3 preset stays; entry points at the new one)
- Modify: provenance JSON (NEW `gold_reselect_provenance.json` beside v3's — gate numbers, mask, criterion, disclosures ×4, holdout-absent, selection-optimism; v3 file untouched)
- Modify: promotion packet doc (append reselect section: why it supersedes v3, caveats; v3 sections untouched)
- Modify: NONE else. PR text via `gh pr edit 4893` (title/body: reselect verdict + disclosures + what merge triggers; NO merge, NO push).

**Interfaces:**
- Consumes: Tasks 1–2 (mask-aware path + staged inputs exist conceptually); frozen gate numbers (quoted from v6b/reselect records — grep-verify each number against the JSONs, never retype from memory).
- Produces: promotable branch state + accurate PR text. Task 4 proves it end-to-end.

- [ ] **Step 1: Draft artifacts (read-first: entry/preset/provenance/packet current text)**

Quote every number from its JSON (shape knees/rates/curvatures, weights, means, sens, mask days, frontier). STOP: any number unlocatable in the records (NEEDS_CONTEXT — never invent).
- [ ] **Step 2: Write + validate (schema loads: settings/presets parse via their loaders; provenance validates if a model exists; PR edit last)**

```bash
git add <settings> <presets> <provenance> <packet>
git commit -m "Promote reselected gold shape branch-side, v3 superseded on-record (#4804)"
gh pr edit 4893 --title "<title>" --body "<body>"
```
(gh failure → STOP with exact error, never worked around.)

---

## Ruling 3 (Plan 17): Task-3b test-pin updates required pre-Task-4 (issued after Task-3 review)

Task-3 review CONFIRMED 3 stale gold test pins (preset-name set EXPECTED+1, :375 literal, flat-synthetic mask harness data) — all stale-because-the-entry-legitimately-changed, zero BTC asserts affected, no artifact contract break. Required fix (Task 3b, TEST FILES ONLY — any production-file hunk = STOP): update the 3 pins to the promoted entry (fail-first RED on the branch, then GREEN; full gold-test files + engine subset green). Task 4 proceeds after. Verdict on Task 3 itself: PASS on artifacts (numbers, scope, disclosures, PR edit, commit).

## Ruling 5 (Plan 17): per-entry trade_start override authorized (issued after Task-4b NEEDS_CONTEXT)

Task-4b correctly stopped: no per-entry `trade_start` support exists (`run_and_write:771` binds from `defaults`; zero `entry.get("trade_start")` repo-wide). Decision (controller, within owner direction "extend gold to 2010, gold only"): option (a) — add a reviewed per-entry `trade_start` override read at the binding site with defaults-fallback (BTC entries resolve identically; BTC-default paired pin mirrors the sell_mask None-pattern), plus the catalog-row/Slapper-layering only if the read-first shows they need it for symmetry (else untouched). Options (b) shared-default change and (c) 2018-rescope are REJECTED (BTC consequences; frozen-gate violation). Rails correction + window override + pin roll (incl. a NEW gold-override/BTC-default paired pin — the coverage gap Task-4b found) land ATOMICALLY in one commit; rails-without-window must never land alone (second-STOP trap). Then Task-4 re-proof runs.

## Ruling 4 (Plan 17): rails defect + 2010 window (issued after Task-4 STOP, schema part superseded by Ruling 5 below)

Task-4 STOP verified by controller: (1) entry `risk_model` stayed `generic_valuation` with 90/1.0 as dead pass-through — Task 3 missed the plan's "risk_model rolling90/z1.0" requirement and the Task-3 review missed the miss. Correction (no new decision): entry risk_model → `rolling_z`. (2) Owner decision 2026-10-02: extend gold's live trade window to 2010-01-01 via per-entry override (gold only, BTC untouched) so the mask zone is in-window — schema authorized by Ruling 5 (the read-first/STOP below is superseded; do NOT stop on missing schema, implement option (a)). Both ride with pin updates (expect RED on entry-content pins), full suites, one atomic settings commit (rails-without-window must never land alone); then Task-4 re-proof runs against the corrected entry.

## Ruling 6 (Plan 17): parameter-free provenance fix (issued after Task-4c STOP triage)

Task-4c STOP triaged CONFIRMED: `generate_tearsheets.py:860` reads `model.coefficients` unconditionally; `RollingZRiskModel` stores only window/z/history (no fit) — first real rolling model through `run_and_write`. Rails/index materialization (:852-859) already works; ONLY provenance recording assumes a fit. Authorized fix (test-first): when the model exposes no coefficients, record its window/z params instead (rolling-branch-only detection, e.g. getattr — fitted BTC/generic paths byte-identical, proven by unmodified-green suites). Scope: provenance hunk + test, nothing else; then Task-4 re-proof runs. 591a26126 stands clean underneath.

### Task 4: Local end-to-end proof + visuals + docs (no push, no merge)

**Files:**
- Create (untracked): `.scratch/gold_tearsheet_reselect_local.json` (live-path output for the updated entry, no push flags — exact no-push invocation from `--help`, never assumed)
- Create (untracked): public/ preview copies per standing visuals rule + served 200s
- Modify: `digiquant/ARCHITECTURE.md` (append-only paragraph in SDCA section: live-path mask support + promotion state + disclosures)
- Verify: full relevant suites + ruff + status.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: proof that the live path serves the reselect candidate with the mask applied (sell-day count matches the gate's 34 true fill-days family — same metric, not rate sign; numbers parity with the gate within rounding or STOP with the divergence).

- [ ] **Step 1: Generate locally + parity checks (entry weights = v4 vector; rails rolling90; mask applied — else STOP)**

Save output untracked. If generation needs network/creds → STOP with NEEDS_CONTEXT (exact call + missing credential).
- [ ] **Step 2: Visuals + docs + verify + commits (ARCH only; outputs/preview state per standing rules)**

---

## Out of scope (not this plan — enforced by review)

- Merge click, `--push-supabase`, nightly runs, credentialed operations.
- New searches/votes/masks/boxes/thresholds/spaces/objectives/geometries; re-selection; sens re-runs; holdout (spent).
- COT/Dow-gold/CPI-oil legs (recon-listed only). Deleting v3 artifacts (history stays).
- Nautilus live-trading enablement; broker paths.

## Self-review

1. Spec coverage: mask-aware live path + BTC-parity gate → Task 1 (read-first with STOPs on schema/builder/window-threading, fail-first with paired BTC-None assert, three minimal edits); DFII10 nightly step → Task 2 (additive-only + pin, mask-built-at-generate-time stated); entry/preset/provenance/packet/PR-text → Task 3 (v3 stays, numbers grep-verified, gh-edit-never-merge); local proof + visuals + docs → Task 4 (mask-applied parity incl. fill-day metric, serve proofs, ARCH).
2. Placeholder scan: file paths, entry/preset/provenance names, box levels, shape values, JSON names, commands are literal-or-read-first (flagged VERIFY-FIRST where the brief guesses at seams). STOPs name trigger + action.
3. Type consistency: `sell_mask` block vs `sell_dates` set vs mask JSON distinguished everywhere; `gold_reselect_provenance.json` vs v3 provenance names distinct; reselect preset name read-first (not invented here — Task 3 reads the file first).
