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
- [ ] Run `pytest tests/ -m unit -k "digiquant" -v` — passes before and after
- [ ] Run `ruff check digiquant/ && ruff format --check digiquant/` — zero errors
- [ ] Confirm no `import pandas` outside the [pandas allowlist](#pandas-allowlist-rem-058059) below
- [ ] Confirm no live-trading path touched (broker adapters, order submission) without human gate
- [ ] Confirm `BacktestResult` Pydantic model is unchanged or versioned if modified

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **Nautilus only**: NautilusTrader is the sole backtest and live-trade engine. Do not add a second backtest path. VectorBT Pro sweeps are Phase 3.
- **Polars except at documented boundaries**: Use Polars for all new data paths. Pandas is allowed only on paths in the allowlist below (Nautilus wrangler, tearsheet Plotly bridge, legacy atlas preload script). Do not add new pandas imports without updating this table.

### Pandas allowlist (REM-058/059)

| Path | Reason | Migration |
|------|--------|-------------|
| `digiquant/nautilus_runner.py` | Nautilus `BarDataWrangler` requires pandas | None — documented boundary |
| `digiquant/olympus/replay/nautilus_portfolio.py` | Same BarDataWrangler boundary for shared-cash portfolio replay (#2784) | None — documented boundary |
| `digiquant/tearsheet.py` | Nautilus `account_report` / `fills_report` are pandas DataFrames | Defer — Plotly quantstats bridge |
| `digiquant/tearsheet_charts.py` | Plotly/quantstats expect pandas Series for rolling stats | Defer — same as tearsheet |
| `digiquant/scripts/atlas/*.py` | Legacy ops: yfinance / pandas-ta / treasury XML (REM-058 allowlist) | Migrate per-script to Polars in [#579](https://github.com/digithings-ai/digithings/issues/579); `compute-technicals.py` Polars date fix (REM-009) |
| `digiquant/scripts/atlas/preload-history.py` | Same atlas ops family | Delegate to `scripts/preload-history.py` (Polars) when touched |
| `digiquant/strategies/bollinger_mr.py` | Nautilus strategy bar helpers | Issue backlog — migrate to stdlib `timedelta` pattern (see `rsi_momentum.py`) |
| `digiquant/strategies/macd_trend.py` | Same | Same |
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

When touching `digiquant/src/digiquant/olympus/`:

1. Read [`ARCHITECTURE.md`](ARCHITECTURE.md) § Atlas + Hermes and
   [`docs/superpowers/specs/2026-06-20-olympus-daily-thesis-design.md`](../docs/superpowers/specs/2026-06-20-olympus-daily-thesis-design.md).
2. Read component guides: [`src/digiquant/olympus/atlas/docs/AGENTS.md`](src/digiquant/olympus/atlas/docs/AGENTS.md),
   [`src/digiquant/olympus/hermes/docs/AGENTS.md`](src/digiquant/olympus/hermes/docs/AGENTS.md).
3. **One graph, one daily cadence** — do not add `OLYMPUS_HERMES_LITE`, `run_type` graph forks,
   or `monthly` synthesis paths. Cost control = `OLYMPUS_MODEL_TIER` + per-artifact `skip`/`edit`/`full`.
4. **Edit-mode extension pattern** (`digiquant.olympus.edit_mode`):
   - Call `resolve_edit_mode(artifact_key, run_date, prior_loader, triage, force_full_rewrite)`
     at node entry.
   - `skip` → shallow-carry prior row (0 LLM); `edit` → load `*-edit.md` skill, expect
     `DocumentPatch`, merge via `merge_document_patch`; `full` → `*-full.md` skill, full body.
   - Prior = `prior_published(run_date, document_key)` (latest `date < run_date`), not calendar
     yesterday only. Stale gap > `OLYMPUS_STALE_FULL_DAYS` (default 7) → `full`.
   - Track B WP13-class shadow (#2616): `digiquant.olympus.attention_plan.plan_attention_shadow`
     records `AttentionPlan` + refresh reasons beside incumbent modes (`off`/`shadow` only;
     never actuates; cannot expand H4 or rewrite H7/H8).
   - Track C glass-box (#1945 / #2622): `attention_plan_io` +
     `attention_plan_graph.maybe_publish_attention_plan_shadow` (Atlas
     `publish_phase`) upsert `attention-plan` on daily runs when triage ran and
     `OLYMPUS_PLANNER_MODE` is `shadow` (default). Never fabricate UI rows without
     a published document; never actuate (`enforce` absent).5. **Hermes extension pattern** (H1–H9): add phases via `build_hermes_phases_thesis`; wire
   `build_grounding` + phase blinding; H7 must not emit weights (`PMDirectionMemo` only); H8
   sizes; H9 `commit_run` is the Hermes terminal — do not add parallel `portfolio_materialize`
   or phase9 evolution on the daily path.
6. Tests: `pytest tests/dq/olympus/ tests/dq/atlas/ tests/dq/hermes/ -m unit -v`

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
- **`SdcaStrategy` is not in `strategies/registry.py`**, the same as
  `m2_liquidity`. Instantiate `SdcaStrategyConfig` directly — do not add a
  `register()` call for it. Its `risk_path` (a parquet of precomputed
  `date`/`risk`) has no sensible static default, so `get_strategy()`'s
  param-merge model doesn't fit. Build that parquet with
  `sdca/risk_index.py::build_risk_index()` + `write_risk_index()`, or the
  `digiquant_build_sdca_risk_index` MCP tool — do not hand-assemble it.
- **`SdcaStrategy.on_bar()` must call `AccumDistCurve.value_at_risk()` and
  mirror `sdca/backtest.py::run_backtest()`'s buy/sell sizing loop, never
  reimplement it.** This is what keeps the Nautilus-run result and the
  standalone parity harness (`tests/dq/strategies/sdca/test_backtest.py`) from
  silently diverging.

### RiskModel providers (#1082)

`strategies/sdca/btc_power_law.py` is the first concrete `RiskModel`
(`BtcPowerLawRiskModel`) — a fitted BTC power-law (RAQQR). Anti-patterns:

- **Never treat `btc_power_law_coefficients.example.json` as a real fit.**
  It is a synthetic placeholder (git-ignored `btc_power_law_coefficients.json`
  doesn't exist yet in most checkouts/environments — no network access to
  BTC price history or the reference artifact was available when this
  provider was built). `load_coefficients()` logs a warning when it falls
  back to the placeholder; don't silence or ignore that warning in code
  reviewing this area — the fitted curve underneath a `SdcaStrategy` run may
  not be real.
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
- The other two #1082 providers (generic per-asset valuation-z, RS-driven
  risk) are not implemented yet.

### Adding a preset

Presets are public, hand-authored `curve_nodes`/`long_only` personalities in
`strategies/sdca/presets.json`, loaded via `strategies/sdca/presets.py`
(`list_presets()`, `load_preset(name)`). To add one:

1. Append an entry to `presets.json`: a 21-element `curve_nodes` array (one
   value per risk node `0, 5, …, 100` — matches `curve.RISK_NODES`), a
   `long_only` bool, and a `description` explaining the personality in plain
   language (not tuned parameters — this is public, documented config, not an
   optimizer output).
2. If `long_only: true`, every `curve_nodes` value must be `>= 0` — a negative
   node in a long-only preset is a contradiction the loader does not catch at
   read time; `tests/dq/strategies/sdca/test_presets.py::test_long_only_preset_never_sells`
   is what catches it.
3. Run `pytest tests/dq/strategies/sdca/test_presets.py -v` — no code changes
   needed for a well-formed entry, `presets.py` reads the file directly.

### SDCA test commands

```bash
# Core engine + presets + Nautilus wrapper config/instantiation tests
pytest -m unit -k "sdca" -v

# Full Nautilus BacktestEngine parity test (gated: needs nautilus_trader installed)
pytest tests/dq/test_strategies.py::TestSdcaStrategyNautilusParity -v
```

---

## digiquant Supabase backend — `core` (#1064)

The digiquant shared backend is the **`core`** Supabase project — the project historically
used by Olympus/Atlas ([`supabase/`](supabase/), `project_id "digiquant-atlas"`), repurposed
(renamed `core`) as the suite-wide backend. It is **not** a separate project: the free-tier
2-project limit is taken by Olympus + the confidential **twelve-x** project. The shared market
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

## Atlas research sandbox image (#396)

`digiquant/Dockerfile.sandbox` is a **separate** image from the digiquant HTTP
service (`digiquant/Dockerfile`). Atlas agents execute Python research / paper-book
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
