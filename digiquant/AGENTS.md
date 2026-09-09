# Agent Guide: digiquant

## Purpose

digiquant is the **deterministic quant engine** of digithings. It owns and executes the ordered pipeline: validate → backtest → optimize → export. No other service may make performance claims (Sharpe, PnL, trade count) without a result originating from this service. It is the sole source of truth for strategy evaluation.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — full pipeline, API surface, data models, Nautilus integration notes
2. [`docs/NAUTILUS_NAVIGATION.md`](docs/NAUTILUS_NAVIGATION.md) — **required** before any Nautilus strategy or backtest change
3. [`docs/NAUTILUS_QUICK_REF.md`](docs/NAUTILUS_QUICK_REF.md) — Nautilus Actor/Bar/Order quick reference
4. [`../AGENTS.md`](../AGENTS.md) — non-negotiable stack-wide rules
5. [`../ROADMAP.md`](../ROADMAP.md) — do not implement VectorBT/Qlib/FinRL until Phase 3
6. [`../docs/agent-backlog/INDEX.md`](../docs/agent-backlog/INDEX.md) — current task queue

---

## Pre-Flight Checklist

Before making any change to `digiquant/`:

- [ ] Read `ARCHITECTURE.md` section for the area you're touching (data, strategies, backtest, optimize, server)
- [ ] Read `docs/NAUTILUS_NAVIGATION.md` if touching any strategy, backtest runner, or Nautilus wrapper
- [ ] If touching Group A books (`positions`, `nav_history`, `position_events`, `portfolio_metrics`), overlay cron, or house GHA writers/readers — read [`docs/ops/HOUSE_BOOK_SCOPE.md`](../docs/ops/HOUSE_BOOK_SCOPE.md)
- [ ] Run `pytest tests/ -m unit -k "digiquant" -v` — passes before and after
- [ ] Run `ruff check digiquant/ && ruff format --check digiquant/` — zero errors
- [ ] Confirm no `import pandas` outside the [pandas allowlist](#pandas-allowlist-rem-058059) below
- [ ] Confirm no live-trading path touched (broker adapters, order submission) without human gate
- [ ] Confirm `BacktestResult` Pydantic model is unchanged or versioned if modified
- [ ] Confirm new Group A reads/writes pin `workspace_id` (house via `eq_house_workspace` / `house_workspace_id()`, overlay via explicit id) — never date-only scans

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **Nautilus only**: NautilusTrader is the sole backtest and live-trade engine. Do not add a second backtest path. VectorBT Pro sweeps are Phase 3.
- **Polars except at documented boundaries**: Use Polars for all new data paths. Pandas is allowed only on paths in the allowlist below (Nautilus wrangler, tearsheet Plotly bridge, legacy research preload script). Do not add new pandas imports without updating this table.

### Pandas allowlist (REM-058/059)

| Path | Reason | Migration |
|------|--------|-------------|
| `digiquant/nautilus_runner.py` | Nautilus `BarDataWrangler` requires pandas | None — documented boundary |
| `digiquant/strategies/sdca/nautilus_evaluator.py` | Same BarDataWrangler boundary for SDCA walk-forward trials (#3174) | None — documented boundary |
| `digiquant/dashboard/replay/nautilus_portfolio.py` | Same BarDataWrangler boundary for shared-cash portfolio replay (#2784) | None — documented boundary |
| `digiquant/tearsheet.py` | Nautilus `account_report` / `fills_report` are pandas DataFrames | Defer — Plotly quantstats bridge |
| `digiquant/tearsheet_extract.py` | Same Nautilus report boundary as `tearsheet.py` (#1185 split) | Defer — same as tearsheet |
| `digiquant/tearsheet_stats.py` | HTML stats from Nautilus/Pandas-origin metrics (#1185) | Defer — same as tearsheet |
| `digiquant/tearsheet_page.py` | HTML page assembly for Plotly tearsheet (#1185) | Defer — same as tearsheet |
| `digiquant/tearsheet_charts.py` | Plotly/quantstats expect pandas Series for rolling stats | Defer — same as tearsheet |
| `digiquant/scripts/research/*.py` | Legacy ops: yfinance / pandas-ta / treasury XML (REM-058 allowlist) | Migrate per-script to Polars in [#579](https://github.com/digithings-ai/digithings/issues/579); `compute-technicals.py` Polars date fix (REM-009) |
| `digiquant/scripts/research/preload-history.py` | Same research ops family | Delegate to `scripts/preload-history.py` (Polars) when touched |
| `digiquant/strategies/bollinger_mr.py` | Nautilus strategy bar helpers | Issue backlog — migrate to stdlib `timedelta` pattern (see `rsi_momentum.py`) |
| `digiquant/strategies/macd_trend.py` | Same | Same |
| `digiquant/strategies/sdca/nautilus_evaluator.py` | Nautilus `BarDataWrangler` for SDCA walk-forward trials (#3174) | None — documented boundary |
| `digiquant/strategies/rsi_momentum.py` | **Migrated** — uses `datetime.timedelta` only | Done (audit PR) |
| `tests/dq/test_strategies.py` | `TestSdcaStrategyNautilusParity` and `TestSdcaRiskIndexNautilusChain` build bars via `BarDataWrangler`, same boundary as `nautilus_runner.py` (#1081, #3168) | None — documented boundary |

- **No perf claims without results**: Never return Sharpe, PnL, or drawdown values from anywhere except a completed `BacktestResult` or `OptimizeResult`.
- **Pipeline ordering is sacrosanct**: validate → backtest → optimize → export. Never skip validation. Never run optimize before backtest.
- **Strategies compile to Nautilus Actor**: All strategies must implement the Nautilus `Actor`/`Strategy` interface. Custom Python strategy logic goes in `strategies/`, not inline in the backtest runner.
- **ADDM drift is wired**: `GET /check_drift` accepts `current_sharpe`; `run_backtest` calls `record_sharpe()`. Heartbeat still needs product wiring to act on `drift_detected`.
- **Human gate on live trading**: Broker adapter code (`digiquant/brokers/`) must never be called from any automated path without an explicit human gate.

---

## Test Commands

```bash
# Unit tests (no stack required)
pytest tests/ -m unit -k "digiquant" -v

# Single strategy test
pytest tests/digiquant/test_strategies.py -v

# Backtest smoke test (requires data file)
digiquant backtest -s ema_cross -S BTC-USD -d digiquant/data/BTC-USD.csv -v

# Optimize smoke test
digiquant optimize -s bollinger_mr -S BTC-USD -d digiquant/data/BTC-USD.csv -m grid -n 10

# Full unit suite
make test-unit

# Lint
ruff check digiquant/ && ruff format --check digiquant/
```

---

## Dashboard (research + portfolio)

Public path is **`/dashboard/`** only (`frontend/dashboard`; ADR-0026). `/dashboard/` is retired — no redirect alias.

When touching `digiquant/src/digiquant/dashboard/` **or** `frontend/dashboard/` Group A queries:

1. Read [`ARCHITECTURE.md`](ARCHITECTURE.md) § research + portfolio and
   [`docs/superpowers/specs/2026-06-20-olympus-daily-thesis-design.md`](../docs/superpowers/specs/2026-06-20-olympus-daily-thesis-design.md).
2. Read **house book scope**: [`docs/ops/HOUSE_BOOK_SCOPE.md`](../docs/ops/HOUSE_BOOK_SCOPE.md) —
   omitted `workspace_id` = house; dashboard uses `houseBook()`; MCP `query_data`
   stamps `HOUSE_BOOK_READ_TABLES`.
3. Read component guides: [`src/digiquant/research/docs/AGENTS.md`](src/digiquant/research/docs/AGENTS.md),
   [`src/digiquant/portfolio/docs/AGENTS.md`](src/digiquant/portfolio/docs/AGENTS.md).
4. **One graph, one daily cadence** — do not add a portfolio-lite env fork, `run_type` graph forks,
   or `monthly` synthesis paths. Cost control = `OLYMPUS_MODEL_TIER` (frozen production env; dual-read `DIGIQUANT_MODEL_TIER`) + per-artifact `skip`/`edit`/`full`.
5. **Edit-mode extension pattern** (`digiquant.dashboard.edit_mode`):
   - Call `resolve_edit_mode(artifact_key, run_date, prior_loader, triage, force_full_rewrite)`
     at node entry.
   - `skip` → shallow-carry prior row (0 LLM); `edit` → load `*-edit.md` skill, expect
     `DocumentPatch`, merge via `merge_document_patch`; `full` → `*-full.md` skill, full body.
   - Prior = `prior_published(run_date, document_key)` (latest `date < run_date`), not calendar
     yesterday only. Stale gap > `OLYMPUS_STALE_FULL_DAYS` (default 7) → `full`.
   - Track B WP13-class shadow (#2616): `digiquant.dashboard.attention_plan.plan_attention_shadow`
     records `AttentionPlan` + refresh reasons beside incumbent modes (`off`/`shadow` only;
     never actuates; cannot expand H4 or rewrite H7/H8).
   - Track C glass-box (#1945 / #2622): `attention_plan_io` +
     `attention_plan_graph.maybe_publish_attention_plan_shadow` (research
     `publish_phase`) upsert `attention-plan` on daily runs when triage ran and
     `OLYMPUS_PLANNER_MODE` is `shadow` (default). Never fabricate UI rows without
     a published document; never actuate (`enforce` absent).
6. **portfolio extension pattern** (H1–H9): add phases via `build_portfolio_phases_thesis`; wire
   `build_grounding` + phase blinding; H7 must not emit weights (`PMDirectionMemo` only); H8
   sizes; H9 `commit_run` is the portfolio terminal — do not add parallel `portfolio_materialize`
   or phase9 evolution on the daily path.
7. Tests: `pytest tests/dq/dashboard/ tests/dq/research/ tests/dq/portfolio/ -m unit -v`

---

## Strategy aliases (#1185)

Canonical map: `digiquant.strategy_aliases` (`STRATEGY_ALIASES`,
`resolve_strategy_name`, `resolve_param_spec_name`). Optimize param-spec keys
may differ from the registry name (`btc_sdca` → `sdca`). When adding an alias:

1. Add it to `STRATEGY_ALIASES` (so optimize/export/CLI resolve without Nautilus).
2. Pass the same names in `register(..., aliases=...)`.
3. If the optimize key differs from the registry name, add `PARAM_SPEC_NAMES`.
4. Do not invent a second private alias dict in `strategy_specs` / `export`.

`sweep.py` was deleted — use `run_optimize(..., param_grid=...)` for grid
evaluation.

---

## SDCA Engine (#1080, #1081)

`strategies/sdca/` is the asset-agnostic Strategic-DCA engine (composite risk →
accumulation/distribution curve → daily backtest). See
[`ARCHITECTURE.md` § SDCA Engine](ARCHITECTURE.md#sdca-engine-1080-1081) for
the full module map.

- **The core engine (`curve.py`, `composite_risk.py`, `risk_model.py`,
  `valuation.py`, `backtest.py`) has zero NautilusTrader dependency.** Only
  `nautilus_strategy.py` imports `nautilus_trader` — don't add a `nautilus_trader`
  import to any other file in this package, or `strategies.sdca` stops being
  importable without the `nautilus` extra.
- **`SdcaStrategy` is registered as `btc_sdca` (#3170)** with `risk_path`-less
  `default_params`. `generate_tearsheets.py` materializes the parquet from the
  already-signal-delayed OHLCV frame (`materialize_sdca_risk_index`) and
  injects `risk_path` via `get_strategy(..., **overrides)`. Direct
  `SdcaStrategyConfig` construction is still valid for tests. Do not pass
  `trade_size` into configs that do not declare it (`config_declares_field`).
  `m2_liquidity` remains unregistered — same runtime-path pattern, not a
  second special case. Research parquets also come from
  `sdca/risk_index.py::build_risk_index()` + `write_risk_index()`, or the
  `digiquant_build_sdca_risk_index` MCP tool — do not hand-assemble them.
- **`SdcaStrategy.on_bar()` must call `AccumDistCurve.value_at_risk()` and
  mirror `sdca/backtest.py::run_backtest()`'s buy/sell sizing loop, never
  reimplement it.** This is what keeps the Nautilus-run result and the
  standalone parity harness (`tests/dq/strategies/sdca/test_backtest.py`) from
  silently diverging.
- **Sizing is remaining-book, not initial.** `size_trade(rate, cash, units)`
  does `buy_usd = cash * rate / 100` and `sell_units = holdings * |rate| / 100`.
  Both `run_backtest` and `on_bar` pass the running cash/holdings, never
  `initial_cash`. A high daily buy rate (balanced `buy_max_rate=8`) compounds
  remaining cash toward dust during a cheap window — that is intended
  remaining-% math, not a percent-of-initial bug, and it is **not** a
  long/short book. Pin: `tests/dq/strategies/sdca/test_remaining_pct.py`.
- **Publish copies #3168 diagnostics** (`rails`, `risk_curve`,
  `cost_basis_curve`, `capital_deployed_curve`, `lump_equity_curve`,
  `flat_dca_equity_curve`) plus a DCA `current_signal` (today's risk, band,
  daily remaining-book rate) onto the tearsheet JSON so the #3172 charts do
  not degrade. Trade KPIs stay `null` for `kind=dca`.
- **Library, not broker live.** `btc_sdca` ships into the public strategy
  library (delayed signals, #1462). Do **not** enable Nautilus live-trading
  or broker adapters for SDCA. Publish uses a spot CASH venue and leaves
  the remaining book open at engine stop. `--push-supabase` is an operator
  step after a real Nautilus generate; do not run it from an agent
  environment.
- **Published `btc_sdca` is a composite valuation index + remaining-book.**
  Keepers **power law + M2 + DXY + weekly log-MACD + weekly/monthly RSI**
  (`valuation=1.0`, `m2=0.5`, `dxy=0.5`, `weekly_macd=0.5`, `weekly_rsi=0.25`)
  are persisted in `settings.json`. SMA band and BTC/ETH RS stay at 0.
  Oscillator z is cycle-scaled (RSI dead-zone + cap; log-MACD sloped top),
  not 90-day rolling z. Preset `btc_optimized` sells (`long_only: false`)
  with a concentrated remaining-book curve (high max daily % of remaining
  cash/coins at the extremes). Walk-forward OOS `beats_flat_dca_oos` is
  still false — in-sample richness, not a proven OOS beat. Allocation
  charts draw MTM allocated % plus fill dots; do not draw a percent-cash
  line (it is the inverse of allocated).
- **Public copy.** User-facing name is **BTC-SDCA** (asset then type; never
  “BTC SDCA Strat”). The other BTC book in the suite is **BTC L/S** — Slapper
  is a true long/short (`enable_short`, net-short, BTC reversal flip), not
  relative strength. Same pattern for **ETH L/S** and **SOL L/S**. The page
  is a strategy (fills chart, latest remaining-book signal, MTM allocated, vs
  buy-and-hold). Honesty lives in notes, not a chip wall. Do not render
  vs-flat DCA as a public KPI (`flat_dca_mark_to_market` is equal remaining-cash
  spend each day, fully deploying by the last bar — not a public comparable).
  Do not render `capital_deployed_pct` as "Deployed". `StrategyNotes` must
  render for SDCA (not slapper-only).

### RiskModel providers (#1082)

`strategies/sdca/btc_power_law.py` is the first concrete `RiskModel`
(`BtcPowerLawRiskModel`) — a fitted BTC power-law (RAQQR). Anti-patterns:

- **Never treat `btc_power_law_coefficients.example.json` as a real fit**
  when the committed `btc_power_law_coefficients.json` is present (#3173).
  `load_coefficients()` still falls back to the placeholder with a warning
  if the real file is deleted. Don't silence that warning.
- **Fit real coefficients via the `digiquant_fit_btc_power_law` MCP tool**
  (or `fit_btc_power_law()` + `save_coefficients()` directly), which sources
  price history through `data/prices/history_cache.py` — the same cache
  every other price consumer uses. Don't write a bespoke fetch path for this.
  (`digiquant_fetch_coinbase_ohlcv`'s CCXT/Coinbase script pipeline writes to
  the *same* `data/price-history/` directory and ticker naming, not a
  separate cache — `history_cache.py` is still the right one to call from a
  new tool because it's the actively-maintained, incrementally-updating
  pipeline every other consumer builds on, not because the data differs.)
- **`low_quantile`/`high_quantile` (default 10th/95th) are an unvalidated
  judgment call**, not verified against the reference artifact's corridor —
  revisit once that artifact is reachable, don't assume the default is
  correct.
- The per-asset ladder is `btc_power_law` → `generic_valuation` →
  `rolling_z` (`sdca/providers.py`, #3175). RS-driven risk is still #1084,
  not this WP. Equity CAPE is #3176 — do not add it here.

### Adding an asset (SDCA framework)

SDCA is a **repurposable framework**, not a Bitcoin-only strategy. The shared
core is generic technicals + composite + two-stage fit + regularize.
Asset-specific series (BTC on-chain SOPR/MVRV, later stock put/call) plug in
on the extra-indicator allowlist.

1. Cache OHLCV in `data/prices/history_cache.py` (never a bespoke fetch).
2. Pick `risk_model`: `btc_power_law` (BTC), `generic_valuation`, or
   `rolling_z`.
3. Pin `SdcaCycleWindows` from that asset's history; set
   `SdcaOscillatorSpec` (RSI / MACD / SMA-band windows) to its cycle.
4. Allowlist extras: generic (`weekly_rsi`, `weekly_macd`, `sma_band`) vs
   plugins (BTC M2/rs_eth/dxy; on-chain #1086 later). No put/call scrape
   in this WP.
5. Stage A backtest keep/drop (`optimize_stage_a_by_backtest` over
   `stage_a_search_names(profile)`) → Stage B → `regularize`. Cycle
   overlap is diagnostic. Platform MCP: `digiquant_fit_sdca_weights` /
   `digiquant_run_optimize` (`strategy_name=sdca`, freeze `*_weight` keys).
   Do not publish until the backtest looks comfortable.
6. Only then add `settings.json`. `SdcaAssetProfile.eth_research_v1()` is
   research-only — not `eth_sdca` in settings, no `--push-supabase`, no
   live-trading. Do not change publish `signal_delay_days`.

On-chain extras (#1086): Bitview/BRK is the free ingest source (`mvrv`,
`asopr_24h`, `puell_multiple`, `rhodl_ratio`; no NUPL; no HTML scrape;
fail-soft). MCP `digiquant_fetch_bitview_series` and CLI
`digiquant onchain fetch-bitview` write parquet under `data/onchain/bitview/`
and optionally upsert `macro_series_observations` (`source=bitview`). Scheduled
job: `.github/workflows/pipeline-digiquant-onchain.yml` (persistent failure
tracker). Local **MVRV-Z** + companion z-series live in
`strategies/sdca/onchain_valuation.py` (`OnChainValuationProvider`) and are
consumable by `compute_composite_risk` — **not published composite votes yet**
(null-rule would halt SDCA on a Bitview gap). Coverage is BTC-rich; ETH/SOL
fall back to basic `rolling_z` via `resolve_sdca_valuation_tier`. Coin Metrics
community CC BY-NC stays research-only.

`pytest -m unit tests/dq/strategies/sdca/test_asset_profile.py` is the
multi-asset smoke (full ETH Coinbase cache if present, else a synthetic
second series — document "add ETH when cache is present"). Do not prefix-
clip QuantReg at 900 days; subsample evenly with `max_fit_rows` if the
fit is slow, and still score every cached day. Oscillator nulls are a
short leading warmup (`documented_warmup_calendar_days`, 105 days for
weekly RSI 14), not a 2018/2021 cliff.

### Adding a preset

Presets are public personalities in `strategies/sdca/presets.json`, loaded via
`strategies/sdca/presets.py` (`list_presets()`, `load_preset(name)`). Since
#3169 they are authored as `SdcaCurveShape` parameters (a dead zone and two
knees), not 21 free nodes. `load_preset()` still returns `SdcaPreset.curve_nodes`
for `SdcaStrategyConfig`.

1. Append an entry to `presets.json` with `long_only`, a `description`, and a
   `shape` object: `buy_max_rate`, `buy_knee_risk`, `sell_knee_risk`,
   `sell_max_rate`, `buy_curvature`, `sell_curvature`. Long-only personalities
   use `sell_max_rate: 0` and `sell_knee_risk: 100`.
2. If `long_only: true`, generated nodes must all be `>= 0` — the loader
   rejects a negative node. `tests/dq/strategies/sdca/test_presets.py::test_long_only_preset_never_sells`
   is the regression net.
3. Run `pytest tests/dq/strategies/sdca/test_presets.py tests/dq/strategies/sdca/test_curve_shape.py -v`.

### Re-running SDCA walk-forward (#3174)

When new BTC history lands, do **not** reuse a full-history rail fit inside the
optimizer (#3173: truncated quadratic log-time fits do not extrapolate).

```bash
# Injected-evaluator unit tests (no Nautilus, no statsmodels fit)
pytest -m unit tests/dq/strategies/sdca/test_walk_forward.py tests/dq/strategies/sdca/test_optimize.py

# Operator run (Nautilus; may SIGABRT on Linux — #42). Never --push-supabase.
PATH="$PWD/.venv/bin:$PATH" python -c "
from pathlib import Path
from digiquant.optimize import run_optimize
from digiquant.strategies.sdca.optimize import persist_btc_optimized, run_sdca_walk_forward
# Prefer run_optimize(strategy_name='sdca', ...) which already refits rails per fold.
"
```

`run_optimize(strategy_name='sdca'|'btc_sdca', ...)` is the MCP/HTTP path
(`digiquant_run_optimize`) — Stage B. Stage A is
`digiquant_fit_sdca_weights` (cycle-window overlap; cannot honestly live
inside `run_optimize`). Objective is maximize `vs_flat_dca_pct` subject to
a 10% capital-deployed floor and a 50% drawdown cap — **not** vs-lump, **not**
Sharpe. Extra-indicator weights (`m2_weight`, `rs_eth_weight`, `dxy_weight`,
`weekly_rsi_weight`, `weekly_macd_weight`, `sma_band_weight`) are searched by
`method=random`/`bayesian` or an explicit `param_grid`; auto-grid holds them
at 0 (valuation-only, current BTC charts) unless Stage A weights are passed
as `strategy_params` (frozen onto every trial). Weekly RSI/MACD/SMA-band z are
computed from **that asset's** close via `technicals_from_ohlcv` (no sibling
file). Place `M2SL.csv`, `ETH-USD.csv`, and/or `DTWEXBGS.csv` next to a BTC
OHLCV file to enable those **BTC-plugin** rails — missing files skip trials
that need them. Two-stage fit: published BTC Stage A
(`optimize_stage_a_by_backtest`) grids every extra with data and keeps
weights by in-sample `vs_flat_dca_pct` (frozen curve; OOS reported, not
used to pick). Cycle overlap (`optimize_stage_a_weights` via
`digiquant_fit_sdca_weights`) is diagnostic. Stage B freezes those
weights and runs this
walk-forward; `persist_two_stage` writes aggressive vs regularized provenance.
Linux Nautilus may SIGABRT (#42) — then inject `evaluate_sdca_trial_curve_sim`
and record that evaluator in provenance. Persist even if OOS vs-flat-DCA is
negative. Do not publish `btc_optimized` / composite variants to digiquant.io
from this WP. No live-trading.

### Strategy research loop

Building a strategy is **trial and error**, not a stack of PRs. Keep one
working branch. The inner loop is: try a change → see how the book
behaves → keep or revert. Creativity lives in *what* you try (indicator,
transform, knee, rate). Speed lives in *not* wrapping each try in a
review/merge cycle.

Do this, in any order the evidence asks for — skip what you already
trust:

- **Engine first.** Confirm remaining-book actually trades through the
  sample (Nautilus halt, dust, pending) *before* hunting extras. A
  simulator that sells in 2025 and an engine stuck in 2023 is not a
  research disagreement — it is a bug.
- **One evaluator per question.** `curve_simulator` is for fast
  add/drop and curve search (Linux-safe, #42). Nautilus tearsheet is
  for “does this book sell / allocate the way we think?” Never mix
  simulator OOS, full-sample vs-flat, and Nautilus fills in one
  sentence. Buy-and-hold is the public comparable.
- **Look at fills.** Allocation step + sized buy/sell dots. If buys
  drip through a bull or sells never cluster at a top, the curve or
  the index is wrong — do not “fix” it with more PRs or more copy.
  No percent-cash line (inverse of allocated).
- **Index then curve, then again.** Add or drop an extra (and its
  *transform* — 90-day rolling-z will sit rich through a bull).
  Re-run `sdca-optimize-curve` on **that** composite. Do not freeze
  weights, fit a curve, then change weights and ship the old curve.
- **Research feeds the next trial**, it does not become the session.
  A catalog (TradingView, on-chain, macro) is a list of *candidates*.
  Pull one, wire data you can actually fetch, look at fills, keep or
  drop. Do not port 27 scripts or open a research PR per indicator.
- **Persist last.** Sidecars and charts are cheap. `settings.json` /
  `btc_optimized` / the public page change when a trial is the
  candidate, not when the search starts. `--push-supabase` stays
  operator-only. Public names (asset then type: **BTC-SDCA**) wait
  until the book looks right.

Anti-patterns from the first BTC-SDCA build:

- A PR per extra hunt, chart, copy pass, and sibling “freeze index”
  vs “widen index” branch — then a day of consolidating GitHub.
- Joint extra search on a curve fitted to power law, then treating
  weight 0 as “extras are useless.”
- Publishing honesty chrome (“power-law remaining-book”) before the
  fills chart looked like buy-cheap / sell-rich.

### Remaining-book curve search

When fills look like a slow drip instead of clustering at bottoms/tops,
search the **curve** on **today's** composite. If you just changed
indicator weights or transforms, re-run this search — do not reuse a
curve fitted to a different index.

```bash
# Linux-safe curve_simulator. Never --push-supabase.
PATH="$PWD/.venv/bin:$PATH" digiquant sdca-optimize-curve \
  --cache-dir data/price-history --signal-delay-days 3 \
  --n-random 400 --seed 42 --sidecar /tmp/sdca_curve_search.json
# Optional: write btc_optimized only if return AND fill concentration both beat
# the published 3% / 25 / 70 curve.
PATH="$PWD/.venv/bin:$PATH" digiquant sdca-optimize-curve \
  --cache-dir data/price-history --persist-preset
```

Search space is `SdcaCurveShape` only (`buy_max_rate`/`sell_max_rate` up to
40%/day, knees inside the published 25/70 dead zone, curvature up to 5).
Objective is `total_return_pct` plus fill concentration. vs-flat-DCA is
logged, never `beats_flat_dca_oos`. Gates require remaining-book identity
and sells in rich windows (including a recent top when the sample has
one).

### SDCA test commands

```bash
# Core engine + presets + Nautilus wrapper config/instantiation tests
pytest -m unit -k "sdca" -v

# Full Nautilus BacktestEngine parity test (gated: needs nautilus_trader installed)
pytest tests/dq/test_strategies.py::TestSdcaStrategyNautilusParity -v
```

### Adding a strategy family to the publish pipeline

`scripts/generate_tearsheets.py` is no longer Slapper-only (#3170). To add a family:

1. Add `"strategy_type": "<family>"` on the `settings.json` entry (omit it to stay
   `slapper`). Put family-specific fields in a nested block named after the type
   (SDCA uses `"sdca": {preset, risk_model, long_only, initial_cash}`).
2. `register()` the Nautilus class with **runtime-only paths omitted** from
   `default_params` (`risk_path`, `signal_path`). Inject those via overrides after
   a materialization hook that reads the **signal-delayed** OHLCV frame, never the
   full cache.
3. Skip `resolve_calibrations()` for non-Slapper families. Record provenance in
   tearsheet notes instead.
4. Pass `trade_size` only when `config_declares_field(name, "trade_size")`.
  5. Nightly `pipeline-digiquant-tearsheets.yml` is the live-library path and
   must stage `export_sdca_macro.py` (M2/DXY siblings) before generate so
   `btc_sdca` weights are not silently dropped. A one-shot operator push is
   `generate_tearsheets.py --strategy btc_sdca --signal-delay-days 3 --push-supabase`
   after a real Nautilus run (#3453). Do not SQL-insert fake metrics.

---

## digiquant Supabase backend — `core` (#1064)

The digiquant shared backend is the **`core`** Supabase project — the project historically
used by dashboard/research ([`supabase/`](supabase/), `project_id "digiquant-research"`), repurposed
(renamed `core`) as the suite-wide backend. It is **not** a separate project: the free-tier
2-project limit is taken by dashboard + the confidential **twelve-x** project. The shared market
datasets already live here; #1064 only **adds** the strategy store
([`supabase/migrations/046_strategy_store.sql`](supabase/migrations/046_strategy_store.sql)).

The strategy-store accessor (`digiquant.data.store`, `build_digiquant_client`) resolves the
standardized `CORE_SUPABASE_URL` / `CORE_SUPABASE_SERVICE_KEY`
([ADR 0022](../docs/adr/0022-supabase-env-naming-standard.md)), falling back to the legacy
`*_DIGIQUANT` and shared `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` names. `CORE_SUPABASE_*`
is a **GitHub org secret** (all repos write `core`) — **never commit values**.

See [`ARCHITECTURE.md` § digiquant Data Layer](ARCHITECTURE.md#digiquant-data-layer--strategy-store--shared-data-1064)
and [`docs/adr/0021-digiquant-supabase-project-topology.md`](../docs/adr/0021-digiquant-supabase-project-topology.md).

---

## research sandbox image (#396)

`digiquant/Dockerfile.sandbox` is a **separate** image from the digiquant HTTP
service (`digiquant/Dockerfile`). research agents execute Python research / paper-book
code inside it. The open-source quant stack is baked at **build time** — do not
`pip install` inside agent runs.

**Scope:** research sandbox only. No live trading, no broker credentials, no
order paths. Optional outbound HTTPS for free data (Yahoo / FRED); never wire
this image to live trading venues.

### Build / run

```bash
# From repo root (context = digiquant/)
docker build -f digiquant/Dockerfile.sandbox -t digiquant-sandbox digiquant

# Or from digiquant/
docker build -f Dockerfile.sandbox -t digiquant-sandbox .

# Smoke — all named imports must succeed
docker run --rm digiquant-sandbox \
  python -c "import skfolio, riskfolio, pandas_ta, arch, alphalens"

# Full package spot-check
docker run --rm digiquant-sandbox python -c "
import pandas_ta, talib, vectorbt
import skfolio, pypfopt, riskfolio, cvxpy
import empyrical, pyfolio, arch, statsmodels, alphalens
import yfinance, pandas_datareader
import polars, numpy, scipy, openpyxl, matplotlib
print('sandbox imports ok')
"

# Agent pattern — run a one-liner or mounted script
docker run --rm digiquant-sandbox python -c "import pandas_ta as ta; print(ta.__version__)"
docker run --rm -v \"\$PWD:/work:ro\" -w /work digiquant-sandbox python my_research.py
```

Manifest: [`requirements.sandbox.txt`](requirements.sandbox.txt). Import notes:

| Package | Import |
|---------|--------|
| `pandas-ta-classic` | `pandas_ta` (shim) or `pandas_ta_classic` |
| `TA-Lib` | `talib` |
| `riskfolio-lib` | `riskfolio` |
| `alphalens-reloaded` | `alphalens` |
| `empyrical-reloaded` / `pyfolio-reloaded` | `empyrical` / `pyfolio` |

**TA-Lib:** modern wheels (`TA-Lib>=0.7`) bundle the C library — no
`libta-lib-dev` on debian slim. Documented in the Dockerfile header.

**yfinance:** Yahoo rate-limits without notice. Prefer
`from yfinance_retry import download_with_retry` (baked at
`/opt/digiquant_sandbox`, on `PYTHONPATH`) over bare `yfinance.download`.

**Image size:** target < 3GB. Measure after a successful local/CI build with
`docker images digiquant-sandbox` — do not invent a size figure.

**Not in scope for #396:** `execute_code` / MCP wrappers (#397), skills library
(#398). Those consume this image later.

See [`ARCHITECTURE.md` § 10](ARCHITECTURE.md#10-docker-and-mcp-composition) for
the sandbox layer in the component diagram.

---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
