# Secular sell-top legs, data-only (Plan 14a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stage the two secular-top legs from the Plan-13 recon as DATA-ONLY additions (staged series + coded z-functions, all weights default 0, no engine changes, no behavior change to any published path), and measure each alone against gold's secular tops — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Background:** Owner premise (2026-10-01): strongly long-biased system, buys on medium-term value timeframe, sells only at secular extremes on a monthly/multi-year timeframe. Recon (same session) found: buy-side legs already wired/staged; sell-side gap = real-rate level + Mayer-style 200w gauge. Engine confirmed single-blend/single-curve (`composite_risk.py:53-57`, `curve.py:59-68`, `backtest.py:160-179`) — decoupled buy/sell voting needs a later engine design (phase b, NOT this plan).

**Pre-registered sign semantics (frozen, not tuned):**
- `real_rate` leg: z = **+**`causal_rolling_z(DFII10 level, window 1260d)` — NO flip. Washout semantics for a long-biased system: real yields at multi-year highs = fear washed out = cheap (+z, buy); deeply negative real rates = crowded fear-bid = rich (−z, sell). (Headwind semantics would flip it; washout is chosen and documented because the system is long-biased and buys washes.) Window 1260d matches the v5 secular rationale (half-swing).
- 200w gauge: Mayer multiple = price / trailing 200-week SMA, measured not voted in this plan (no thresholds frozen, no engine consumption — Task 2 output is analysis, thresholds would be a phase-b decision).

**Tech Stack:** Python, Polars, Pydantic v2, pytest (`-m unit`), ruff (line length 100). Simulator-only; no network in tests (staging runs are operator-style, recorded).

## Global Constraints

- Data-only: new series staging + new catalog functions + weights-model fields defaulting 0.0. NO edits to `composite_risk.py`, `curve.py`, `curve_shape.py`, `backtest.py`, `nautilus_strategy.py`, `risk_index.py`, `providers.py`, settings/presets/provenance, nightly workflows. Any need to touch those = STOP with NEEDS_CONTEXT.
- New weights default 0.0 everywhere (BTC + gold published paths byte-identical — proven by unmodified-green suites).
- No pandas, pydantic v2, ruff 100 on touched files. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push. No merge/push (owner-side).

---

### Task 1: Real-rate leg (DFII10 staging + catalog z + tests)

**Files:**
- Modify: the macro-staging path (read-first: how M2SL/WALCL/T5YIE get staged — `export_sdca_macro.py` SERIES_FILES? sealed R2 panel? mirror the T5YIE path exactly; DFII10 is daily FRED H.15 like DGS10)
- Modify: `digiquant/src/digiquant/strategies/sdca/indicator_catalog.py` (new `real_rate_z` function mirroring `uup_z` MINUS the flip + `SdcaCompositeWeights.real_rate` field default 0.0 + loader/`enabled_extras` wiring mirroring `uup` — read the uup sites first and mirror each)
- Modify: nearest catalog/weights test file (grep `uup` in tests/ — extend, don't create, if a natural home exists; else colocate with the v4-era gold macro tests)
- Create (untracked): staged DFII10 series file (location per the mirrored path)

**Interfaces:**
- Consumes: FRED DFII10 (free/keyless, live-verified 2026-10-01 by recon).
- Produces: staged series + coded voteless leg. Task 3 measures it.

- [ ] **Step 1: Read-first (staging path + uup mirror sites, no edits)**

Record: (a) exact staging flow for T5YIE (commands/files/commitments — run the staging for DFII10 the same way); (b) every `uup` site in catalog/loader/weights/tests (function, weights field, `_require_pair`/sources wiring, `enabled_extras`, display name). If DFII10 cannot be fetched keyless, STOP with NEEDS_CONTEXT (exact error) — do not substitute DGS10−T10YIE decomposition without approval (that is a different leg).

- [ ] **Step 2: Failing tests first**

Tests (mirror uup tests): `real_rate_z` rises with yields (high yield → +z/cheap) and falls deeply negative when yields crater (washout semantics, no flip — assert the SIGN explicitly against a uup-style flipped expectation); weights default 0.0; missing-series behavior mirrors uup (same fail-soft/skip rule — read it, don't invent). Expect FAIL (no function/field).

- [ ] **Step 3: Implement (staging + catalog + wiring, nothing else)**

Stage DFII10 (full depth, provenance: first/last/rowcount recorded in report). Implement `real_rate_z(dates, dfii10, window=1260)` + weights field + loader wiring + display name (mirror uup sites one-for-one except the flip). STOP branches: staging path differs structurally from recon (NEEDS_CONTEXT); any required engine/settings edit (NEEDS_CONTEXT, don't spread).

- [ ] **Step 4: Run + lint + commit**

Full catalog/weights/macro test files + engine subset `-m unit -q` green UNMODIFIED except the new tests. Ruff clean. Then:
```bash
git add <staging script if tracked> digiquant/src/digiquant/strategies/sdca/indicator_catalog.py <test file(s)>
git commit -m "Stage real-rate leg for secular tops, voteless default (#4804)"
```
(Staged data file stays untracked if that matches the T5YIE precedent — verify precedent, don't assume; record either way.)

---

### Task 2: 200w gauge measurement (analysis only, no engine consumption)

**Files:**
- Create: `digiquant/scripts/measure_gold_mayer_multiple.py` (standalone offline analysis — reads GLD-USD.csv, no engine imports beyond what's needed for dates/prices; MUST NOT import composite/curve/backtest)
- Create (untracked): `digiquant/.scratch/gold_mayer_multiple.json` (multiple time series + event table)
- Modify: NONE (zero production-file diff — proven by `git diff --stat` showing only the new script)

**Interfaces:**
- Consumes: `digiquant/data/price-history/GLD-USD.csv` (2004→present; 1980 predates it — 2011/2015/2020/2022/now only, stated).
- Produces: event table + whipsaw read. Task 3 judges it.

- [ ] **Step 1: Write the script**

200-week SMA on GLD closes (1000 trading days; completed weeks only, causal — state the week-assembly rule in a comment), multiple = price / 200wma. Output JSON: full multiple series + event rows (value at Sep 2011 top, Dec 2015 bottom, Aug 2020 high, Oct 2022 dip, latest bar) + whipsaw stats (days multiple > 1.5 and > 1.7 outside ±6mo of the 2011 top — i.e. would a threshold have fired during the grind?). NO thresholds frozen, NO recommendations — numbers only.

- [ ] **Step 2: Run + record**

`PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/measure_gold_mayer_multiple.py`. Record the event table verbatim + whipsaw counts in the report. If GLD history can't support a 200w window before ~2008, state the effective window (first valid date) — no adjustment, no alternative window tried (trying windows = tuning; this plan measures ONE).

- [ ] **Step 3: Lint + commit (script only, output untracked)**

Ruff clean, then:
```bash
git add digiquant/scripts/measure_gold_mayer_multiple.py
git commit -m "Measure gold 200w Mayer multiple, analysis only (#4804)"
```

---

### Task 3: Verdict (go/no-go for phase-b engine design) + docs

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (append-only paragraph: both legs' firing evidence + verdict either way)
- Verify: relevant suites + ruff + status.

**Interfaces:**
- Consumes: Tasks 1–2 evidence.
- Produces: go/no-go + paragraph. No new runs.

- [ ] **Step 1: Judge (no new runs)**

GO for phase-b design requires BOTH: (a) real-rate z at/near multi-year-high (cheap) readings spanning the 2015 bottom zone AND at/near multi-year-low (rich) readings spanning the 2011 top zone on the staged full-depth series (quote the values — "fires" means top-decile of its own history at those events, judged against its full history, not tuned); (b) 200w multiple ≥ 1.5 at the 2011 top with < 5% of grind-days above the same level (i.e. selective, not whipsaw). Anything less = NO-GO with the exact failed half named. Either way, NO engine design in this task — the verdict is the product.

- [ ] **Step 2: Docs + verify + commit**

ARCH paragraph (legs, firing table, verdict). Suite + ruff. Commit ARCH:
```bash
git add digiquant/ARCHITECTURE.md
git commit -m "Record secular-leg firing verdict for phase-b decision (#4804)"
```

---

## Out of scope (not this plan — enforced by review)

- Engine extension design (phase b, separate decision on a GO verdict only).
- Weight/param tuning of any kind (defaults 0, windows frozen, thresholds unjudged).
- COT / Dow-gold / CPI-oil legs (second-order, new ingest — recon-listed, not tasked).
- COT-style weekly-cadence ingest, WGC flows, cost-floor models.
- Holdout (spent), promotion packets, nightly, credentials, merge.

## Self-review

1. Spec coverage: staging + z + tests → Task 1 (read-first T5YIE/uup mirror, fail-first with sign assert, voteless default, STOPs for fetch failure/structural drift/engine spread); measurement → Task 2 (one window, causal weeks, event table + whipsaw, zero production diff); verdict + docs → Task 3 (conjunctive GO bar with quoted values, NO-GO names the half, no design work).
2. Placeholder scan: DFII10, window 1260, 200w/1000d, file paths, JSON names, commands, 1.5/1.7 levels, 5% whipsaw bar are literal. STOPs name trigger + action.
3. Type consistency: `real_rate` field name vs `real_rate_z` function vs DFII10 series distinguished everywhere; `gold_mayer_multiple.json` / `measure_gold_mayer_multiple.py` identical in tasks; washout (no-flip) semantics identical in plan header, tests, and implementation.
