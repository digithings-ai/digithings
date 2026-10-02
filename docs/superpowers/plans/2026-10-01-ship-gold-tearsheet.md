# Ship gold SDCA tearsheet (Plan 11: live path + staging + local proof + PR) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the BTC-hardcoded SDCA live path for the `gold_sdca` entry, wire nightly staging for GLD/UUP/M2SL, prove a local end-to-end gold tearsheet, and open the merge PR — stopping before merge and before any Supabase push (both owner-side; push happens via the nightly workflow post-merge with CI creds) — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Architecture:** Minimal generalization, BTC parity. The SDCA branch iterates the entry's own `indicator_weights` (instead of the 7-key block), dispatches rails via `resolve_sdca_risk_model(entry risk_model)` (instead of hardcoded `BtcPowerLawRiskModel`), and runs the drop-guard over all nonzero weights (instead of m2/dxy/rs_eth). Staging: yfinance `fetch-quotes` (keyless, proven in Plan 2) for GLD+UUP with the probe-first stem rule; M2SL already covered by `export_sdca_macro`. No new indicators, no new rails, no bar/weight/shape changes anywhere.

**Tech Stack:** Python, pytest (`-m unit`), ruff (line length 100), GitHub Actions (existing workflow patterns), `gh` CLI (PR open only).

**Spec:** Plan 10 work order (`digiquant/.scratch/gold_live_path_workorder.md`, D1–D4 — decisions made HERE, not deferred): D1 GLD price source = yfinance fetch-quotes (keyless; R2 sealed generations as the later optimization, not this plan); D2 UUP staging = same price-fetch step (NOT SERIES_FILES — price files come from the price step; manifest can't carry OHLCV); D3 weights passthrough = iterate entry `indicator_weights`; D4 rails dispatch = `resolve_sdca_risk_model` on the entry's `risk_model`. Gap sites (recon-held): `generate_tearsheets.py:793-801` (7-key block), `:814-818` (drop-guard triple), `:161-168,834` (hardcoded BTC rails), `:855-859` (provenance weights); `fetch_coinbase.py:28-30` (BTC/ETH/SOL only — NOT extended; GLD comes from the yfinance step instead); promotion artifacts on-branch (settings `gold_sdca`, preset `gold_optimized`, provenance with holdout −21.16%).

## Global Constraints

- BTC parity is the hard gate: every pre-existing BTC tearsheet/preset/optimize test passes UNMODIFIED. Any red on those = STOP, not fix-forward on live behavior.
- No Supabase push from anywhere in this plan (`--push-supabase` never invoked; no service-role creds exist here anyway). No merge (PR opened, not merged). No nightly edits beyond ADDITIVE workflow steps (no existing step modified).
- Stem rule (Plan 2 Ruling 3 carries): consumers use exact stems (`GLD-USD.csv`, `UUP.csv`). Probe `GLD-USD` via yfinance FIRST; if it 404s like the other suffixed ETFs, fetch plain `GLD` + `cp -f` to the suffixed stem each run (full overwrite, no incremental keying — document why in the workflow comment + report).
- ruff line length 100 on touched files only. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.

---

### Task 1: Live-path generalization (BTC parity gated)

**Files:**
- Modify: `digiquant/scripts/generate_tearsheets.py` (SDCA branch: weights passthrough, rails dispatch, drop-guard, provenance — 4 sites, nothing else)
- Modify: nearest offline test file for the SDCA branch (find it first: grep generate_tearsheets in tests/ — extend, don't create, if a natural home exists)

**Interfaces:**
- Consumes: settings entries (`btc_sdca` + `gold_sdca`), `resolve_sdca_risk_model`, `drop_extras_missing_sources` (already generic over weights — verify, don't assume).
- Produces: entry-driven SDCA tearsheets with BTC outputs byte-identical (proven by unmodified green, not by assertion).

- [ ] **Step 1: Read the four sites + the test home (no edits yet)**

Read `generate_tearsheets.py:785-860` (weights block, drop-guard, rails build, provenance), `:155-175` (rails helper), and grep `generate_tearsheets` under tests/ for the SDCA test home. Record exact current text of each site in the report. If any site differs structurally from recon (e.g. already generalized), STOP with NEEDS_CONTEXT quoting actual vs expected.

- [ ] **Step 2: Generalize (four minimal edits, BTC behavior provably unchanged)**

1. Weights `:793-801` → build from `entry["sdca"]["indicator_weights"]` (full dict passthrough into the existing weights model — read how the dict becomes `SdcaCompositeWeights` today; if via explicit kwargs, switch to `SdcaCompositeWeights(**{k: v for k, v in entry_weights.items() if k in KNOWN_FIELDS})` where KNOWN_FIELDS derives from the model (never a hardcoded list that rots — derive it).
2. Rails `:161-168,834` → `resolve_sdca_risk_model(entry risk_model, dates, price, ...)` dispatching on the entry's `risk_model` (`btc_power_law` → today's path byte-identical; `generic_valuation` → runtime fit). If the current code path for `btc_power_law` cannot be preserved byte-identically through the dispatcher, STOP with NEEDS_CONTEXT (do not rewire BTC rails by hand).
3. Drop-guard `:814-818` → iterate nonzero entry weights (same zeroing semantics, all names, not three).
4. Provenance `:855-859` → name all nonzero entry weights + preset + risk_model (same format, more names).
BTC byte-identity argument (in report, verified by suite): same entry in → same code path → same outputs; the unmodified BTC tests are the proof, not new assertions.

- [ ] **Step 3: Gold-path test (offline, canned)**

Extend the SDCA test home with a gold test: canned `gold_sdca`-shaped entry (v3 weights incl. uup 0.5) through the same code path with stubbed rails/framework seams the existing tests already use (mirror their seam pattern — read first, no new harness). Assert: uup survives the drop-guard (not zeroed when its file would exist — assert on weights/model level, not disk), rails dispatch selects generic_valuation (assert type/model-name, not fit values), provenance names uup. NO live fits, NO network, NO disk staging in tests.

- [ ] **Step 4: Run + lint + commit**

Run: the SDCA test home FULL file(s) + `tests/dq/strategies/sdca/test_presets.py` + `test_asset_profile.py` + engine subset (`-m unit -q`).
Expected: all green UNMODIFIED (any red on pre-existing BTC tests = STOP per the hard gate).

Ruff check + format-check touched files.
Expected: clean.

```bash
git add digiquant/scripts/generate_tearsheets.py <test file(s)>
git commit -m "Generalize SDCA tearsheet path beyond BTC (#4804)"
```

(Commit body: BTC byte-identical by unmodified-green suite; gold entry now servable; live push/nightly still pending owner steps.)

---

### Task 2: Nightly staging steps (additive workflow edits)

**Files:**
- Modify: `.github/workflows/pipeline-digiquant-tearsheets.yml` (ADD a GLD/UUP fetch step + M2SL already covered — read the workflow first; additive only)
- Create: `tests/scripts/test_tearsheets_gold_staging_workflow.py` (pin test mirroring the Plan-3 workflow-pin pattern: step presence, tickers/stems, no secret additions, no existing-step modification — decide yaml vs substring by the `import yaml` probe precedent)

**Interfaces:**
- Consumes: yfinance fetch-quotes (keyless); stem rule; export_sdca_macro (unchanged, M2SL covered).
- Produces: nightly-staged GLD-USD.csv + UUP.csv next to the existing BTC/M2SL steps.

- [ ] **Step 1: Probe GLD-USD resolvability (determines the step shape)**

Run: `cd digiquant && ../.venv/bin/python -m digiquant prices fetch-quotes --tickers GLD-USD --cache-dir /tmp/probe-gldusd --period 5d && wc -l /tmp/probe-gldusd/GLD-USD.csv; cd ..` (plus `UUP-USD` for completeness — expect 404 per Plan-2 rule; UUP stays plain-stem regardless).
Branch (in the report, then implement the winning shape):
A. GLD-USD resolves → step runs `fetch-quotes --tickers GLD-USD,UUP --cache-dir <same dir as the BTC step>` (incremental, keyed correctly).
B. GLD-USD 404s → step runs `fetch-quotes --tickers GLD,UUP` into a temp dir + `cp -f GLD.csv <cache>/GLD-USD.csv UUP.csv <cache>/UUP.csv` (full overwrite each run; comment in the yaml explains the keying break). Clean up temp.
Either way the BTC fetch step is untouched (new step after it). M2SL needs no step (macro script covers it — assert SERIES_FILES still contains M2SL by reading, don't assume).

- [ ] **Step 2: Pin test first (TDD on yaml)**

Create the pin test per the Plan-3 precedent (read `tests/scripts/test_enrich_gold_refresh_workflow.py` first for the house pattern): asserts the new step exists by name, references fetch-quotes with the winning tickers/stems, adds no secrets, and fails on the current workflow (RED). Run to verify RED.

- [ ] **Step 3: Implement the workflow step + GREEN + lint + commit**

Edit the workflow (additive step only — `git diff` must show +lines in one hunk region, zero modifications to existing steps; any required modification → STOP with NEEDS_CONTEXT). Re-run pin test → GREEN. yaml validity is proven by the pin test's parse (no separate linter available — state that).

```bash
git add .github/workflows/pipeline-digiquant-tearsheets.yml tests/scripts/test_tearsheets_gold_staging_workflow.py
git commit -m "Stage GLD/UUP for gold tearsheets at nightly (#4804)"
```

---

### Task 3: Local end-to-end proof + PR open (no merge, no push)

**Files:**
- Create (untracked): `digiquant/.scratch/gold_tearsheet_local.json` (proof output, never committed)
- Modify: NONE (proof only). PR opened via `gh` (no merge).

**Interfaces:**
- Consumes: Tasks 1–2 (generalized branch + research-staged files: GLD-USD.csv, UUP.csv, M2SL.csv all on disk from Plans 1–2).
- Produces: a locally generated gold tearsheet + an openlegs-and-all PR. Push/merge stay owner-side.

- [ ] **Step 1: Generate the gold tearsheet locally (no push flags)**

Run the tearsheet generator for the gold entry WITHOUT any push/supabase/dispatch flags (read its CLI first for the exact no-push invocation — `--no-push`? absence of `--push-supabase`? exact command from `--help`, never assumed). Expect: exit 0, output containing slug `gold_sdca` (or the entry key), weights == v3 vector, rails generic_valuation (not BTC power law), numbers sane (compare mean/shape keys against the honest-v3 record — same values within rounding, else STOP: the live path diverges from research). Save output to `.scratch/gold_tearsheet_local.json` (untracked). If generation requires network/creds at any point, STOP with NEEDS_CONTEXT (exact call + missing credential) — do not stub around it.

- [ ] **Step 2: Merge-readiness + PR base routing**

Check `scripts/project_routing.json` for the digiquant component's base (two-hop module branch vs direct develop — read, don't assume); `git fetch origin`; confirm the branch rebases cleanly onto the routed base WITHOUT actually rebasing (dry check: `git merge-base --is-ancestor` reasoning + `git log --oneline origin/<base>..HEAD | wc -l` for size). Draft the PR body (title, Fixes #4804 linkage, plan lineage Plans 1–11, holdout −21.16% disclosed, what merge triggers: nightly staging + push via CI creds, live-path generalization active for gold entry).

- [ ] **Step 3: Open the PR (no merge) + report**

```bash
gh pr create --title "<title>" --body "<draft>" --base <routed-base> --head task/4804-sdca-strategy-for-gold--gld
```

Then report: PR number + URL, merge-readiness (CI pending, conflict state, review-coverage note per CODE_REVIEW_POLICY — in-session reviews on record via SDD packages + final reviews; Bugbot/metered bots are owner-side), what merge triggers operationally, and the residual owner list (merge click, nightly verification of first gold push, holdout/gate numbers unchanged by merge). If `gh` is unauthenticated or 403s, STOP with NEEDS_CONTEXT (exact error) — do not fake it, do not merge by other means.

---

## Out of scope (not this plan — enforced by review)

- Merge click, `--push-supabase` (any venue), nightly workflow runs, credentialed operations.
- New votes/rails/shapes/bars/indicators; gate runs; holdout (spent); backfill redesign.
- `fetch_coinbase.py` extension (GLD comes from yfinance by design decision D1).
- R2-sealed price reads as the staging source (later optimization, noted in the workflow comment if shape B wins).

---

### Task 4: Strategy-registry gap fix + re-proof (added post-Task-3 STOP)

**Context (why this task exists):** Task 3's proof run raised `ValueError: Unknown strategy: gold_sdca` at `nautilus_strategy.py:360` — a fifth hardcoded site the recon missed (strategy registry). Task-1's test faked `run_nautilus`, so the gap was never exercised. Data/risk/calibration stages pass; only registration blocks.

**Files:**
- Modify: the strategy registry module containing `nautilus_strategy.py:360` (read it first — register `gold_sdca` with GOLD curve defaults/nodes, never BTC nodes)
- Modify: the Task-1 test (replace the `run_nautilus` fake with a registry-level assertion AT MINIMUM; if a full unfaked live-path test is feasible offline in reasonable time, prefer it — record the choice)
- Create (untracked): re-run proof output (same `.scratch/gold_tearsheet_local.json` path — first successful generation, not a re-run of anything spent)

**Interfaces:**
- Consumes: v3 gated shape (nodes), gold entry definition.
- Produces: registered strategy + green proof run. No other live-path changes.

**Steps:**

- [ ] **Step 1: Read the registry (no edits yet)**

Read the registry module around `:360`: registration shape (name → what? curve nodes? evaluator params?), how `btc_sdca` is registered (exact lines to mirror), and where gold curve defaults come from (v3 gated shape — read from the honest JSON, never re-derive). Record in the report. If registration requires more than a data entry (logic branches on strategy name elsewhere — grep `btc_sdca` across `digiquant/src/digiquant/` for other hardcoded sites), list every site: registry-only fixes proceed; additional logic branches → STOP with NEEDS_CONTEXT (site list) instead of spreading.

- [ ] **Step 2: Register + test (TDD where the seam allows)**

Register `gold_sdca` mirroring the btc entry with gold nodes. Test: assert registry resolves `gold_sdca` to the v3 gated nodes (exact values) AND does not disturb `btc_sdca` resolution (paired assert — the parity habit). Then re-run the Task-3 proof command verbatim (same no-push invocation): expect exit 0 + output JSON with slug/weights/rails/numbers parity per Task 3's check (same rounding rule). First successful generation — the failed attempt never produced output, so no reserve is spent (state that reasoning explicitly; the holdout reserve is a different asset and untouched regardless).

- [ ] **Step 3: Lint + commit (registry + test only; output untracked)**

Ruff check + format-check touched files.
Expected: clean. Engine/test suites for the touched areas green (name them in the report).

```bash
git add <registry module> <test file(s)>
git commit -m "Register gold_sdca strategy with v3 curve (#4804)"
```

**Out of scope for this task:** any other hardcoded site found in Step 1 beyond the registry (STOP, don't spread); the rebase + PR (Task 5).

---

### Task 5: Rebase onto module/digiquant + open PR (no merge, no push-supabase)

**Files:** Whatever conflicts (strict rules below). No feature code.

**Interfaces:**
- Consumes: branch at Task-4 tip; `origin/module/digiquant` (or the routed base's remote ref — verify remote state first).
- Produces: rebased branch + open PR. Merge + push stay owner-side.

**Steps:**

- [ ] **Step 1: Pre-flight (no mutations)**

`git fetch origin`; `git branch -r --contains HEAD` (expect empty — never pushed); `gh auth status` (expect authed per Task-3 report — re-verify, don't assume); read the routed base ref and its drift (`git log --oneline <base>..HEAD | wc -l` was ~40 ours; `git log --oneline HEAD..<base> | wc -l` = their drift, ~75 per Task-3 report — record both). Confirm the base is `module/digiquant` per `scripts/project_routing.json` (re-read — routing may have changed with the AGENTS.md update).

- [ ] **Step 2: Rebase with Plan-5-grade rules**

`git rebase origin/module/digiquant` (exact ref from Step 1). Conflict rules: ours-wins ONLY on gold-exclusive files (scripts/run_gold_*, gold tests, gold docs, settings/presets/provenance gold entries, workflow gold step); theirs-wins on everything shared UNLESS the hunk is ours from Plans 7-11 engine/live-path work (walk_forward peak field, neighbor key, lookback/cap params, tearsheet generalization, registry entry — these must survive; resolve hunk-by-hunk with the report citing each); any hunk mixing both inseparably → STOP with NEEDS_CONTEXT quoting it. NEVER force-push (branch unpushed — nothing to force). NEVER merge (rebase only).

- [ ] **Step 3: Baseline green + PR open**

Full unit selection per Plan 11 Task-3's suite list + ruff on conflict-resolved files (stash-prove any failure). Then:
```bash
gh pr create --title "Gold SDCA v3 tearsheet (strategy + live path + staging)" --body "<draft: Fixes #4804 lineage, holdout −21.16% disclosed, merge triggers nightly staging + CI-cred push, live-path generalization active>" --base <routed-base> --head task/4804-sdca-strategy-for-gold--gld
```
Report: PR number + URL, CI state, conflict summary, review-coverage note, residual owner list (merge click, nightly first-push verification). gh failure → STOP with exact error (never worked around). No merge under any circumstance.

## Self-review

1. Spec coverage: live-path generalization + BTC-parity gate → Task 1 (read-first + unmodified-green hard gate + offline gold test); staging steps + pin → Task 2 (probe-first stem rule, additive-only, M2SL asserted); local proof + routed PR → Task 3 (exact no-push invocation, research-parity check, no merge/push). Decisions D1–D4 are made in Technical Architecture above (yfinance / price-step / passthrough / dispatch), each with its why.
2. Placeholder scan: file paths, line refs, command shapes, JSON names, commit messages are literal. STOPs (structural drift, BTC red, probe branches, creds/network contact, gh failure, second holdout) name trigger + action. "Same values within rounding" is verified by comparison, not assumed.
3. Type consistency: `gold_sdca` / `gold_optimized` / GLD-USD.csv / UUP.csv / M2SL.csv identical in tasks and triggers; v3 weights/shape referenced from the honest record; no new names invented (rails dispatch reuses the entry's existing `risk_model` key).
