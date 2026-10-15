## 5. Internal Architecture

> Split out of [digiquant/ARCHITECTURE.md](../../ARCHITECTURE.md) (DIG-3399). Prose is unchanged. Relative links were adjusted for this directory.

### LangGraph Pipeline

The pipeline graph is compiled fresh on every `run_quant_workflow()` call (no reuse of a compiled instance). Each invocation is synchronous; the caller blocks until all nodes complete.

```
START
  |
  v
[validate] ─── error ──► END
  |
  v (ok)
[backtest] ─── error ──► END
  |
  ├── run_optimize=False, run_export=False ──► END
  ├── run_optimize=False, run_export=True ──► [export] ──► END
  └── run_optimize=True ──►
       |
       v
    [optimize] ─── error ──► END
       |
       ├── run_export=False ──► END
       └── run_export=True ──►
              |
              v
           [export] ──► END
```

Conditional routing is implemented in `route_after_validate`, `route_after_backtest`, and `route_after_optimize`. The `DIGIQUANT_ALLOW_EXPORT` env var provides a global kill switch for the export node independently of the request body's `run_export` flag.

The `trace` key uses LangGraph's `Annotated[list, add]` reducer so each node appends its step record without overwriting. Callers receive the full trace in the response, making the pipeline auditable step-by-step.

### NautilusTrader Actor/MessageBus Pattern

Each strategy in the registry is a `Strategy` subclass (which inherits from `Actor`). The lifecycle within a backtest is:

1. `BacktestEngine` is instantiated with venue, instrument, bars, and starting balance
2. `engine.add_strategy(strategy)` registers the strategy's message subscriptions
3. `engine.run()` drives the internal event loop: for each bar, the engine publishes a `Bar` event on the MessageBus; all subscribers with matching `BarType` receive it via `on_bar()`
4. Strategies call `self.submit_order()` which goes through the simulated venue for fill simulation
5. After `run()` completes, `engine.trader.generate_order_fills_report()` and `generate_account_report()` provide structured output
6. `engine.dispose()` frees internal resources

digiquant calls this pattern in `_build_engine()` in `nautilus_runner.py`. One engine instance is created per backtest run and disposed immediately after metric extraction. There is no engine reuse across runs.

**Default position sizing is instrument-aware.** The venue starts with `STARTING_BALANCE_USD` ($1M) cash. When a caller does not pass `trade_size`, `_build_engine()` derives one via `_default_trade_size()`: `floor(STARTING_BALANCE_USD * DEFAULT_NOTIONAL_FRACTION / first_bar_price)`, clamped to a minimum of 1 unit. This keeps per-trade notional at a fixed fraction (default 2%) of equity rather than a fixed unit count. A fixed count (the old `Decimal(1000)`) silently over-leveraged high-priced instruments — 1000 BTC units at ~$10k+ on a $1M account is 10–100x leverage, so Nautilus halted the whole run with `AccountBalanceNegative` after a handful of bars and returned a misleading 1-trade result. An explicit caller `trade_size` always overrides the default. Regression coverage: `tests/dq/test_default_trade_size.py`.

### Strategy Registry

Static aliases live in `strategy_aliases.py` (`STRATEGY_ALIASES`: alias →
registry canonical; `PARAM_SPEC_NAMES`: registry canonical →
`STRATEGY_PARAM_SPECS` key when they differ — today only `btc_sdca` → `sdca`).
`resolve_strategy_name` / `resolve_param_spec_name` are the public resolvers
used by CLI, optimize, export, and tests. Do not add a second private alias
dict.

`strategies/registry.py` maintains `_REGISTRY` (name → `StrategySpec`) and
runtime `_ALIASES` from `register(..., aliases=...)`. `resolve_strategy_name`
prefers the static map, then runtime aliases. Registration is done at import
time in each strategy module. The registry does not persist between processes;
optimization workers (when `ProcessPoolExecutor` is used) import the strategy
modules fresh in each subprocess.

**Extension pattern:** add the alias to `STRATEGY_ALIASES` (so optimize/export
work without Nautilus), pass the same names in `register(..., aliases=...)`
for `list_strategies`, and if the optimize param-spec key differs from the
registry name, add a `PARAM_SPEC_NAMES` entry.

`StrategySpec` holds:
- `strategy_cls`: the `Strategy` subclass
- `config_cls`: the `StrategyConfig` subclass
- `default_params`: default values merged with caller overrides
- `description`: human-readable summary

`get_strategy()` resolves aliases, looks up the spec, merges `default_params` with caller overrides and required fields (`instrument_id`, `bar_type`), instantiates `config_cls(**params)`, and returns `(strategy_instance, config)`. `trade_size` is applied only when the config class declares that field (`config_declares_field`, #3170).

### SDCA Engine (#1080, #1081)

`strategies/sdca/` is the generic, asset-agnostic Strategic-DCA engine: composite
risk score → accumulation/distribution curve → daily backtest vs. lump-sum
buy-&-hold. Reverse-engineered from the owner's BTC SDCA artifact but with the
BTC valuation model factored out — the core engine (`curve.py`,
`composite_risk.py`, `risk_model.py`, `valuation.py`, `backtest.py`) has **zero
NautilusTrader dependency and zero BTC-specific constants in its valuation
path**, unlike every other entry in the strategy table above.
`sdca/nautilus_strategy.py` (#1081) is the one file in the package that does
depend on NautilusTrader — it wraps the engine as `SdcaStrategyConfig`/
`SdcaStrategy`, following the same precompute-then-drive pattern as
`m2_liquidity.py`: a Polars DataFrame and a `RiskModel` cannot live in a frozen
`StrategyConfig` (msgspec struct), so the caller runs
`sdca/risk_index.py::build_risk_index()` (#3168) upstream (rails →
`valuation_z_score()` → `compute_composite_risk()`), writes the two-column
`date`/`risk` parquet with `write_risk_index()`, and passes its path in as
`risk_path`. The MCP tool `digiquant_build_sdca_risk_index` is that upstream
for cached price history; a notebook is no longer required. `on_start()` loads that
parquet into a `date -> risk` map (validating the `date`/`risk` columns are
present, rejecting duplicate dates, casting a `pl.Datetime` `date` column
to `pl.Date` — `iter_rows()` otherwise yields `datetime.datetime` keys that
never equal the `datetime.date` `on_bar()` looks up with; any other non-Date
dtype raises — rejecting any null `date` (would otherwise become an
unreachable `None` dict key), and requiring `risk` to be numeric and, where
non-null, finite: a string column loads without error and only fails later as
a `TypeError` inside `AccumDistCurve.value_at_risk()`, and NaN/±inf pass
`is_numeric()` but reach that same call as a non-finite float; a null `risk`
is kept as an explicit no-data day. `on_bar()` looks up the day's risk,
converts it to a trade rate via `AccumDistCurve.value_at_risk()`, and sizes
the trade via the shared `sdca/backtest.py::size_trade()` helper — both
`run_backtest()` and `on_bar()` call this one function, so the Nautilus
**backtest** and the standalone parity harness never diverge. This wrapper
is not wired to broker live-trading; do not enable that path. **The rate is
a percent of the remaining book, never of initial cash or of the original
position:** `buy_usd = remaining_cash * rate / 100` and
`sell_units = remaining_holdings * |rate| / 100`, each clamped so a buy
cannot exceed cash and a sell cannot exceed units held (#2552). Two
consecutive 50% days therefore leave 25% of the prior remaining cash (or
holdings), not zero. When remaining-book size falls below the instrument
`size_increment`, `on_bar()` skips the order instead of letting Nautilus
`make_qty` raise (dust after a cheap window). SDCA is **not** a long/short book. Pin:
`tests/dq/strategies/sdca/test_remaining_pct.py`. `long_only=True` clamps the rate
to `>= 0` regardless of the curve's own sign, as a safety override independent
of which curve is configured. `on_bar()` skips sizing a new order while a
prior one is still open (`_order_pending`, cleared on
fill-complete/canceled/rejected/expired/denied), so two bars can never size
off the same unreserved cash/asset_units. Fill-complete also fires when the
leftover is below `size_increment` (quantization dust must not freeze the
book). A pending flag whose bar date is in the past is canceled so a later
distribute day can still sell. Buys size from quote-precision-floored cash so a
sub-tick remainder cannot overdraft 2-decimal venue cash — Nautilus otherwise
halts the whole backtest (`AccountBalanceNegative`); that is why the published
book never reached 2025. Shadow `_cash`/`_asset_units` are
updated from real `OrderFilled` events (`on_order_filled()`), not the
pre-submission estimate, so they track Nautilus's actual quantity-quantized
execution state rather than drifting from it; a fill's `commission` is also
deducted from `_cash` when denominated in the instrument's quote currency —
a fee paid in a different currency (e.g. the base asset) is left untouched
rather than misapplied, since this shadow accounting has no conversion rate
for it.
Like `m2_liquidity`, **SDCA's `risk_path` has no static default** — it is
produced from a specific `RiskModel` run on a specific OHLCV window. As of
#3170 `btc_sdca` *is* registered, with `risk_path` omitted from
`default_params` and injected at publish time via `get_strategy(..., **overrides)`
after `generate_tearsheets.materialize_sdca_risk_index()` writes a parquet from
the already-`apply_signal_delay()`-truncated frame (so the index cannot leak
bars beyond the published window, #1462). Nautilus then sees **only bars from
`trade_start`** on a **spot `CurrencyPair` + `AccountType.CASH`** venue (not
the Slapper margin perpetual): remaining quote is spent, remaining base is
held. `on_stop()` cancels open orders but does **not** `close_all_positions`
— flattening would invent a round-trip that is not the DCA product. Fill
replay seeds any pre-window fills onto the opening book, then walks the
published calendar. Round-trip `trades_from_positions` is skipped for SDCA
(an open spot book leaves pandas NA on `ts_closed`). `m2_liquidity` stays unregistered;
`trade_size` is only passed into configs that declare it
(`registry.config_declares_field`).

`strategies/sdca/presets.py` (backed by `presets.json`) ships named
personalities as public config — `conservative_hold`, `balanced`,
`aggressive_accumulate` (long-only, increasingly aggressive accumulation) and
`accumulate_and_distribute` (signed curve). Since #3169 these are authored as
`SdcaCurveShape` parameters (dead zone + two knees + curvatures), not 21 free
nodes; `load_preset(name)` still returns an `SdcaPreset` whose `curve_nodes`
are generated at load so `AccumDistCurve` / `SdcaStrategyConfig` stay unchanged.
These are documented personalities, not optimized parameters — except
`btc_optimized` (#3174), which is the walk-forward winner plus a provenance
sidecar (`btc_optimized_provenance.json`). Published `btc_sdca` uses this
distribute curve (`sell_max_rate=3`, `long_only: false`) after a full extra
catalog search that kept **no** extras on in-sample vs-flat-DCA (valuation
rails only — not `balanced` long-only). OOS
`beats_flat_dca_oos` remains false — not a digiquant.io OOS claim. To add a preset:
append a `shape` object plus `long_only` and `description` to `presets.json`;
`SdcaPreset` validates node count (always 21 after generation) and, if
`long_only` is `true`, that every node is `>= 0` at load time. The four
personalities cannot reproduce the old plateau-then-decay node lists (curvature
≥ 1 has no flat region at the extreme) — see #3169.

**This module is a CI-only parity harness, not a second backtest engine.**
`digiquant/AGENTS.md` is explicit that NautilusTrader is the sole backtest and
live-trade engine and that PnL/Sharpe/drawdown must never be returned from
anywhere but a completed `BacktestResult`/`OptimizeResult`. `run_backtest()`
here does not violate that: it exists only so the allocation math (curve,
composite-risk, valuation) can be unit-tested deterministically against known
reference numbers in milliseconds, without a data fetch or Nautilus's actor/bar
infrastructure — see the issue #1080 acceptance criteria (`pytest -m unit -k
sdca`, parity fixture). Its `SdcaBacktestReport` must never be surfaced to
users or dashboards as an actual backtest result. **`nautilus_strategy.py`
(#1081) calls `AccumDistCurve.value_at_risk()` and `size_trade()` directly
rather than reimplementing them** — that is what keeps this module and the
real Nautilus backtest from silently
diverging into two sources of truth for the same allocation decision.
`build_risk_index()` / `write_risk_index()` (`sdca/risk_index.py`, #3168)
are the caller's upstream of `SdcaStrategy` (to build the `risk_path`
parquet), the same way `m2_liquidity`'s own signal computation happens outside
its `Strategy` class. The MCP tool `digiquant_build_sdca_risk_index` is that
upstream for cached price history.

| File | Role |
|---|---|
| `sdca/valuation.py` | `valuation_z_score(price, low, median, high)` — log-space position of price within the `RiskModel` rails, in `[-3, 3]` (cheap = +3, rich = −3). The default/primary indicator. Validates finite, positive rails with `low < median < high` on rows where all four inputs are present; a row with any null input passes through as null. |
| `sdca/risk_model.py` | `RiskModel` — a `runtime_checkable` `Protocol` with one method, `rails(dates) -> pl.DataFrame` (`low`/`median`/`high` columns). Any object with a matching `rails()` satisfies it structurally; the engine never imports a concrete provider. |
| `sdca/providers.py` | String selector `btc_power_law` \| `generic_valuation` \| `rolling_z` → `resolve_sdca_risk_model()` (#3175). |
| `sdca/onchain_valuation.py` | On-chain-enhanced valuation tier (#1086). Local MVRV-Z (causal expanding z of `−mvrv`) plus aSOPR / Puell / RHODL z → `IndicatorWeight` votes consumable by `compute_composite_risk`. `OnChainValuationProvider` loads Bitview parquet; `resolve_sdca_valuation_tier` falls back to basic `RollingZRiskModel` when coverage is thin (ETH/SOL) or the cache is empty. **Not** enabled in published `btc_sdca` weights yet (composite null-rule). |
| `sdca/quantile_rails.py` | Shared QuantReg + rearrangement + span-widen helpers used by generic valuation. |
| `sdca/generic_valuation.py` | Per-asset log-price trend rails from the first cached bar (not BTC genesis). Short history widens the corridor. `max_fit_rows` (optional) evenly subsamples QuantReg across the **full** span — rails/scores still cover every input date. Never a 900-day prefix (that ended Coinbase BTC in January 2018). If `log_quadratic` IRLS does not converge (observed on decade-scale ETH), retry `log_linear` on the same window and record it in `notes`. |
| `sdca/rolling_z.py` | Short-series fallback / basic valuation tier (#1086): causal rolling log-price mean ± z·std as rails. |
| `sdca/asset_profile.py` | `SdcaAssetProfile` — per-asset `symbol`, `risk_model`, `SdcaOscillatorSpec`, `cycle_windows`, extra-indicator allowlist, `signal_delay_days` (default 0; publish delay stays in `generate_tearsheets`). Factories: `btc_v1()`, `eth_research_v1()` (research-only, not in `settings.json`). `daily_closes_from_cache` / `technicals_from_ohlcv` are the shared OHLCV path (full cache, no 900-day cap). `union_date_range` is the overlay x-axis helper — union of spans, not an inner join that would clip BTC to ETH. |
| `sdca/btc_power_law.py` | `BtcPowerLawRiskModel` — the first concrete `RiskModel` (#1082): fits 7 quantile rails (`q01`…`q99`) as `price_q(t) = 10 ** (c + a*x + b*x**2)`, `x = ln(days_since_genesis(t)) - mu`, one quantile regression (`statsmodels.QuantReg`, lazily imported) per rail. `rails()`/`rails_full()` sort each row's fitted quantiles ascending (rearrangement method) so independently-fit curves never cross. `fit_btc_power_law()`/`save_coefficients()`/`load_coefficients()` handle fitting and JSON persistence; `load_coefficients()` prefers the real fit (`btc_power_law_coefficients.json`, committed as of #3173) and falls back to the checked-in synthetic placeholder (`btc_power_law_coefficients.example.json`) with a warning. The `digiquant_fit_btc_power_law` MCP tool is the orchestration layer — this module has no data-fetching or MCP dependency of its own. `low_quantile`/`high_quantile` (default `q10`/`q95`) pick which fitted rails map to the protocol's `low`/`high`; this default and the model itself are unvalidated against the reference artifact — network access to it was blocked in the environment #1082 was built in. |
| `sdca/composite_risk.py` | `IndicatorWeight` (strict Pydantic v2 model: `name`, `z: pl.Series`, `weight`, `enabled`) and `compute_composite_risk()` — weight-normalized blend of enabled indicators' z-scores into `composite_z` (`[-3, 3]`) and `risk` (`[0, 100]`, 0 = max buy, 100 = max sell). Formula: `composite_z = clip(Σ(zᵢ·wᵢ)/Σ(wᵢ), -3, 3)`, `risk = 50 − composite_z×50/3`. Weight-0 members are omitted (`enabled`/weight 0), so `0 × null` cannot wipe a solo extra. Rejects duplicate enabled names and a non-finite/zero total weight. |
| `sdca/indicator_catalog.py` | Named extras: **generic technicals** `weekly_rsi` (MTF weekly+monthly dead-zone) / `weekly_macd` (weekly log-MACD) / `sma_band` plus **BTC-plugin** **m2** / **rs_eth** / **dxy**. `SdcaCompositeWeights` defaults `valuation=1`, extras `0`. Published `btc_sdca` weights live in `settings.json` (sidecar `btc_richer_composite.json`). M2 YoY and DXY rolling-z run on the **full** FRED/DXY calendar, then align onto BTC dates — do not `shift(365)` after joining onto Coinbase days (that amputates leading years). `rs_eth` still needs overlapping BTC/ETH so its warmup is ETH-list-date bound. `allowlist=` from `SdcaAssetProfile.extra_indicators` blocks BTC plugins on a second asset. Omitted: Mayer/200w, alpha residual, on-chain MVRV/SOPR (#1086), equity CAPE (#3176), put/call, RS rotation pool (#1084), pi-cycle (wrong-signed in 2025). |
| `sdca/price_oscillators.py` | `SdcaOscillatorSpec` + weekly/monthly resample + SMA-band z. Completed ISO weeks / calendar months only; `join_asof(..., strategy="backward")`. Weekly RSI uses a **dead zone + cap** (mid-cycle 30–80 is near 0; RSI 85 is max-sell). Weekly MACD is **log-MACD** with a sloped top cap, not 52-week histogram z. `mtf_rsi_z` blends weekly+monthly into the `weekly_rsi` extra. |
| `sdca/cycle_windows.py` | Per-asset pin sets. `btc_v1()` (2017/2021/2025 highs, 2018/2022 lows, ±45d). `eth_research_v1()` (2018-01-13 / 2018-12-14 / 2021-11-10 / 2022-06-18 — ETH's June 2022 trough, not BTC's November). Stage A must not invent ad-hoc date lists. |
| `sdca/stage_a.py` | Weight search that maximizes cycle overlap: mean risk in peak windows minus mean risk in trough windows, plus accumulate/distribute band fractions. Equal objective prefers fewer extras then higher `valuation` (parsimony). Default `search_names` is the full extra catalog; missing `extra_z` series skip those combos. |
| `sdca/weight_search.py` | Stage A keep/drop by **in-sample** walk-forward `vs_flat_dca_pct` with a frozen curve (legacy joint 0/0.5/1 grid). `optimize_stage_1_survivor_weights` searches survivors only on a `(0, 1]` grid (no 0 — turning an extra off cannot cheaply beat power law) and ranks by **OOS** vs-flat plus Stage B capital/drawdown feasibility. Searches every extra that has data (`search_names_with_data`). Rails are fit once per fold. |
| `sdca/fit_weights.py` | Platform helper for Stage A: `resolve_sdca_profile` + `fit_sdca_weights_from_cache` (cached OHLCV → valuation-z → `optimize_stage_a_weights` → `regularize_weights`). MCP tool `digiquant_fit_sdca_weights`. |
| `data/onchain/bitview.py` | Fail-soft Bitview/BRK `day1` client (`mvrv` / `asopr_24h` / `puell_multiple` / `rhodl_ratio`). HTTP-free `series_data_to_frame`. MCP tool `digiquant_fetch_bitview_series`. Library auto-fetch kill-switch `DIGIQUANT_BITVIEW_FETCH=0` (not a secret; MCP invoke is already opt-in). Hosted bitview.space is optional / no SLA. BRK MIT; Coin Metrics community CC BY-NC is research-only (not fetched). |
| `data/onchain/ingest.py` | Scheduled/CLI path (#1086): `ingest_bitview` → parquet under `data/onchain/bitview/` + optional `macro_series_observations` upsert (`source=bitview`). `frame_to_macro_rows` is HTTP-free. Workflow: `pipeline-digiquant-onchain.yml` (daily 22:40 UTC, persistent failure tracker). |
| `sdca/stage_0.py` | Solo-indicator remaining-book books. Each catalog extra and power law (`valuation` code id; user-facing **power law**) gets a one-hot index (unused members omitted). Curve search via `run_stage_b_frozen` / `curve_simulator`. Keep extras that beat named baseline `power_law_solo` on the same walk-forward OOS folds (plus Stage B capital/drawdown feasibility); drop never-sell dumps. IS is diagnostic. `beats_flat_dca_oos` stays false on this sidecar. Operator: `python -m digiquant.strategies.sdca.stage_0` or `digiquant sdca-stage0`. |
| `sdca/curve_sim.py` | Injected Stage B evaluator via `run_backtest` when Nautilus SIGABRTs (#42). Provenance records `evaluator=curve_simulator`. Not a published backtest. |
| `sdca/regularize.py` | Round Stage A weights to tenths (or 0.05) and renormalize; shrink curve max rates and round them to one decimal. |
| `sdca/two_stage.py` | Freeze Stage A weights, run existing walk-forward curve search, persist `{stem}_aggressive.json` + `{stem}_regularized.json` (default stem `btc_composite`; a stem with path separators raises). Stage 0 uses stem `btc_solo_then_combine` so the package dir is a safe `--out-dir`. |
| `sdca/curve.py` | `AccumDistCurve` — 21-node (risk 0, 5, …, 100) piecewise-linear map from risk to a daily trade rate (% of remaining cash on buys, % of remaining holdings on sells). `value_at_risk()` interpolates and clamps risk to `[0, 100]`, rejecting non-finite risk. Nodes are fully configurable and must be finite: all-positive = long-only accumulation, signed = accumulation + distribution. The no-arg default (`DEFAULT_BTC_NODES`) is the issue's documented BTC-reference curve shape, not a hardcoded valuation constant — callers targeting another asset pass their own `nodes`. This is the **runtime** representation; it is unchanged by #3169. |
| `sdca/curve_shape.py` | `SdcaCurveShape` (frozen Pydantic v2, #3169) — the **authoring and optimization** surface. Six parameters (`buy_max_rate`, `buy_knee_risk`, `sell_knee_risk`, `sell_max_rate`, `buy_curvature`, `sell_curvature`) generate the 21 nodes via `to_nodes()`. Enforces a non-empty dead zone, sign/monotonicity, and `*_max_rate <= 100` (the generated-path answer to #2552). The raw `AccumDistCurve` constructor stays unbounded. |
| `sdca/backtest.py` | `run_backtest(dates, price, risk, curve, initial_cash) -> (SdcaBacktestReport, pl.DataFrame)` — the daily state loop and its strict Pydantic v2 summary report. `size_trade()` is the remaining-book sizer (`buy_usd = cash * rate/100`, `sell_units = holdings * |rate|/100`). Validates non-empty, equal-length inputs; a non-null, strictly-increasing `dates` series (#2539, #2544); and a finite, positive, non-null price series and `initial_cash` before running. Export frame includes `flat_dca_value` (#3171); the report's `vs_flat_dca_pct` is ×100, same as `vs_lump_pct`. CI-only — never the published number. |
| `sdca/dca_metrics.py` | Schema 1.3 DCA block from Nautilus fills + daily MTM (`breakdown_from_daily`, `fills_from_nautilus_report`). Publish path uses this; tests assert parity with `SdcaBacktestReport`. Overlays include `allocated_pct_curve` (MTM % in the asset, never `capital_deployed`) and `fill_markers` (`|trade_usd|/portfolio`). |
| `sdca/chart_series.py` | Allocation %, fill-dot sizing, power-law display names, knee lookup, reconstruction from 1.3 payloads that lack the new overlay keys. Does not emit a cash-% series (inverse of allocated). |
| `sdca/risk_index.py` | `build_risk_index(dates, price, risk_model, extra_indicators=None, valuation_weight=1.0) -> pl.DataFrame` and `write_risk_index(df, path)` (#3168). Pure wiring: `risk_model.rails()` → `valuation_z_score()` → optional `IndicatorWeight(name="valuation")` + extras from `indicator_catalog` → `compute_composite_risk()`. Weight-0 valuation is **omitted** from the blend so a Stage 0 solo extra is not nulled by `0 × null`. Returns `date`/`risk` plus diagnostics (`price`, `low`, `median`, `high`, `valuation_z`, `composite_z`, and `{name}_z` for each extra). Default extras-off matches a single-indicator index. |
| `sdca/nautilus_strategy.py` | `SdcaStrategyConfig` (frozen `StrategyConfig`: `instrument_id`, `bar_type`, `initial_cash`, `risk_path`, `curve_nodes` default `DEFAULT_BTC_NODES`, `long_only` default `False`) and `SdcaStrategy(Strategy)` — the NautilusTrader wrapper (#1081). Registered as `btc_sdca` (#3170) with `risk_path` omitted from `default_params`. `risk_path` is produced by `sdca/risk_index.py` (#3168), not assembled by hand. Not wired to broker live-trading. |
| `sdca/presets.py` / `sdca/presets.json` | `SdcaPreset` (frozen Pydantic v2 model: `curve_nodes`, `long_only`, `description`, optional `shape`, validated at load time), `list_presets() -> list[str]`, `load_preset(name) -> SdcaPreset` — named public curve personalities. Since #3169, `presets.json` stores `SdcaCurveShape` parameters; nodes are generated at load. `btc_optimized` (#3174) is the walk-forward slot. |
| `sdca/walk_forward.py` | Walk-forward folds, held-out tail, DCA-native objective (`vs_flat_dca_pct` s.t. capital floor + drawdown cap). Rails **must** be refit on each fold's IS window (#3173). Extra-z is a full-calendar causal precompute sliced per window (no OOS refit, no leakage). |
| `sdca/optimize.py` | Search loop, sensitivity, `persist_btc_optimized()`, `OptimizeResult` mapping. Injected `SdcaTrialEvaluator` — never `SdcaBacktestReport`. Random/bayesian search extra-indicator weights in `[0, 1]` (composite already normalizes). Auto-grid holds extras at 0. Sibling files `M2SL.csv` / `ETH-USD.csv` / `DTWEXBGS.csv` next to the BTC CSV enable those extras. |
| `sdca/curve_optimize.py` | Remaining-book **curve** search on a **frozen** composite (does not re-search extras). The persisted `btc_optimized` shape was searched on power law + M2 + DXY, then applied to the published richer index (those plus weekly log-MACD + RSI). Objective is `total_return_pct` (buy-and-hold is the public comparable; vs-flat is logged only). Gates: not long-only, has sells including 2025, remaining-book identity, buys in the cheap band, sells in the rich band. `beats_flat_dca_oos` is always false here (in-sample). CLI: `digiquant sdca-optimize-curve`. Persist `btc_optimized` only with `--persist-preset` **and** a beat on return **and** concentration. Never `--push-supabase`. |
| `sdca/nautilus_evaluator.py` | Production fitness: Nautilus fills → `dca_metrics`. pandas only at the BarDataWrangler boundary. |
| `charts/sdca.py` | matplotlib diagnostic figures (equity vs hold, index+knees, indicator multiples, allocation step + fill dots). Allocation draws MTM allocated % only — not a cash line. Optional `matplotlib` extra. |
| `sdca/btc_optimized_provenance.json` | Fit window, folds, objective, OOS vs-flat-DCA, sensitivity. Honest even when OOS is negative. |

**Valuation tiers (#1086).** Two ladders sit beside the rail providers:

- **Basic (any asset)** — `RollingZRiskModel` / `generic_valuation` (std-dev
  bands / %-from-MA style). Always available from cached OHLCV.
- **Enhanced (BTC)** — Bitview/BRK on-chain z (`mvrv_z` computed locally from
  `mvrv`, plus `asopr` / `puell` / `rhodl`) via `OnChainValuationProvider`.
  Scheduled ingest: `pipeline-digiquant-onchain.yml` → parquet +
  `macro_series_observations` (`source=bitview`). Coverage map: BTC rich;
  ETH/SOL none → `resolve_sdca_valuation_tier` returns basic. Sources /
  licensing: see `docs/research/sdca-btc-onchain-valuation.md` (BRK MIT;
  Coin Metrics community CC BY-NC research-only). **Not** enabled as
  published composite votes yet — enable only after skip-missing exists.

**Composite-risk null rule.** If any *enabled* indicator's z-score is null on a
day, `composite_z` and `risk` are null that day too — `compute_composite_risk`
uses `pl.sum_horizontal(..., ignore_nulls=False)` so there is never a partial
blend. Weight `0` means the indicator is **not enabled**, so a missing M2/DXY/ETH
row cannot null a valuation-only day. `run_backtest` treats a null-risk day as a
no-trade day: state (cash, holdings) carries forward unchanged, but the day is
still marked to market.

**Composite formula (BTC charts default to a single rail).**

```
composite_z = clip( Σ_i (z_i · w_i) / Σ_i w_i , -3, 3 )
risk        = 50 − composite_z × 50/3
```

`z_i` are daily series in `[-3, 3]` (cheap = +3, rich = −3). Published
`btc_sdca.sdca.indicator_weights` is a composite (power law 1.0, M2 0.5, DXY 0.5, weekly log-MACD 0.5, weekly/monthly RSI 0.25) after re-specifying oscillator transforms. SMA band / BTC/ETH RS stay 0. The catalog / `SdcaCompositeWeights` model default remains valuation-only until a caller enables extras. Weekly log-MACD is no longer a 52-week histogram z. `beats_flat_dca_oos` stays false.
**sma_band sign:** close below the 90-day SMA (in rolling-σ units) is cheap
(+z); above is rich (−z). Raw realized vol is unsigned and is not used.
**Alpha** vs the power-law median is omitted (collinear with `valuation_z`);
alpha vs a slow SMA is Mayer-like and also omitted.
The MCP tool `digiquant_build_sdca_risk_index` and `build_risk_index()` use
that default unless callers pass extras. Walk-forward (`method=random` /
explicit `param_grid`) searches the extra weights; auto-grid does not, so a
default optimize run still matches the power-law-only chart.

**Two-stage fit.** Published BTC extras were originally dropped by Stage A
(`optimize_stage_a_by_backtest`) on **in-sample** vs-flat with a frozen
power-law curve. The operator path is now **solo-then-combine**: Stage 0
(`stage_0.run_stage_0`) fits a remaining-book curve to each extra and to
power law alone; extras must beat named baseline `power_law_solo` on the
**same walk-forward OOS folds** (plus Stage B capital floor / drawdown
feasibility, matching walk-forward ranking) and must sell. IS vs-flat is
reported, not the keep rule. If no extra beats OOS, power-law-only remains
published — do not force extras back in. Stage 1
(`optimize_stage_1_survivor_weights`) then searches survivors on a `(0, 1]`
grid (no 0) and Stage B (`run_stage_b_frozen`) + `regularize` retunes the
combined curve. The operator default writes sidecars only
(`btc_stage0.json`, `btc_stage1_weights.json`,
`btc_solo_then_combine_{aggressive,regularized}.json`). `settings.json` is
overwritten only with `--persist-settings` **and** combined OOS not worse
than the published sidecar — a 2-trial Stage B is not a published-weight
flip. `beats_flat_dca_oos` is true only when that combined run's mean OOS
vs-flat is actually positive. Cycle-window overlap
(`stage_a.optimize_stage_a_weights`) remains a diagnostic.
`stage_a_search_names(btc_v1())` includes BTC plugins; ETH research stays
generic technicals only. Charts still plot weight-0 extras; user-facing
copy says **power law**, not that unused series voted. The aggressive fit
will overfit — that is expected. Do not `--push-supabase`.

**How to add an asset.** The reusable core is technicals + composite +
two-stage weight/curve fit + regularize. Extra series per asset is manual
research; do not scrape put/call or paid on-chain here.

1. Cache daily OHLCV for the ticker via `history_cache.py` (same causal
   ISO-week / as-of rules as BTC). `daily_closes_from_cache` is the shared
   loader — full history, never a 900-day prefix. Overlay BTC+ETH with
   `union_date_range` (shared xlim); do not inner-join to the shorter asset.
2. Pick a rail provider: `btc_power_law` (BTC only), `generic_valuation`
   (log-price trend from the first bar), or `rolling_z` (short history).
3. Pin `SdcaCycleWindows` from that asset's documented peaks/troughs
   (±45d). Calibrate `SdcaOscillatorSpec` windows to its cycle (long-term,
   or medium-term if it persistently trends up).
4. Allowlist extras: generic technicals (`weekly_rsi` / `weekly_macd` /
   `sma_band`) vs asset-specific plugins (BTC: M2 / rs_eth / DXY; on-chain
   z via `OnChainValuationProvider` — research only until skip-missing;
   equity put/call later). Do not enable BTC plugins on a second asset.
5. Run Stage 0 (solo OOS vs power-law) → Stage 1 (survivor weights, no 0
   on the grid) → Stage B (walk-forward curve) → regularize. Legacy Stage A
   IS keep/drop and cycle overlap stay diagnostic.
   Trust the composite as a top/bottom indicator only when that historical
   backtest looks comfortable.
6. Only then consider a `settings.json` entry. `eth_research_v1()` is
   research-only — not published, no `--push-supabase`, no live-trading.
   Public `signal_delay_days` stays on the tearsheet publish path (#1462);
   the profile default is 0.

**Backtest state is a sequential Python loop, not a vectorized Polars
expression** — `cash`/`asset_units` are running balances that each day's buy/sell
depends on, which Polars' columnar model doesn't express cleanly. Inputs
(`dates`, `price`, `risk`) and the per-day export frame are Polars per the
Polars-only convention; only the intermediate accumulator is plain Python. This
mirrors how `nautilus_strategy.py`'s `SdcaStrategy.on_bar()` (#1081) also
processes bars one at a time, driven by real Nautilus bar events rather than a
Python `for` loop.

Per-day export frame columns (`asset_units` rather than the issue's literal
`btc_units` pseudocode name, to match the module's asset-agnostic design):
`date`, `price`, `risk`, `rate`, `daily_trade_usd` (signed: positive = bought,
negative = sold), `cash`, `asset_units`, `net_deployed` (`initial_cash - cash`),
`portfolio_value` (`cash + asset_units * price`), `buy_hold_value` (the
lump-sum benchmark: all
`initial_cash` deployed at day-0 price, marked to market thereafter),
`flat_dca_value` (equal remaining-cash spend each day, #3171).
`SdcaBacktestReport` adds `total_pnl`, `vs_lump_usd`, `vs_flat_dca_usd`, and
fields whose shared `_pct` suffix spans **two unit systems**: `total_return_pct`,
`vs_lump_pct`, and `vs_flat_dca_pct` are true percents (×100, so `-15.0` means
−15%), while `dca_max_drawdown_pct` / `buy_hold_max_drawdown_pct` are negative
*fractions* (`-0.15` for a 15% drawdown — `_max_drawdown_pct` applies no ×100).
The drawdown pair is therefore **not** interchangeable with
`BacktestResult.max_drawdown_pct`,
which is a negative percent — check each field's own docstring before comparing them. Also
`buy_days`/`sell_days`/`no_trade_days`, and `avg_risk`/`avg_rate` (means over
non-null days only).

### Causal trade-levels engine (Track E, #137)

`data/prices/levels.py` computes deterministic entry/stop/target candidates
from an OHLC frame and a direction. It is **pure Polars, no I/O**, and every
derivation is causal — the value at bar *i* is a function of bars ``≤ i`` only,
which `tests/dq/data/test_levels.py::test_augment_is_causal_at_every_row`
asserts by recomputing over truncated prefixes:

- **Wilder ATR / true range** live in `data/prices/_primitives.py` and are
  shared with `technicals.py` (one implementation, not two).
- **Regime scaling** — `regime = atr / SMA(atr, regime_len)` clamped to
  `k_regime_bounds` (default `(0.75, 1.5)`); `k_eff = k_base * regime`, so a
  high-volatility regime widens the ATR stop and a quiet one tightens it.
- **Fractal pivots** — a bar is a strict `fractal_width`-bar fractal high/low;
  detection looks forward but the exposed `piv_high` / `piv_low` columns are
  `shift(fractal_width)`, i.e. visible only once the pivot was confirmable.
- **Donchian** — `don_high_prev` / `don_low_prev` are `rolling_max/min(len)`
  `.shift(1)`, so the channel never includes the current bar.
- **S/R clustering** — confirmed pivots within `cluster_atr * ATR` merge into
  support (low edge) / resistance (high edge) zones.

**Branch preference:** pivot structure → Donchian channel → ATR. A structural
stop is only used when it sits on the correct side of the reference price and
the nearest opposite structure clears `rr_floor`; otherwise the engine falls
back to the `k_eff * ATR` stop. Take-profit rungs are the `tp_rmultiples`
(default `1R/2R/3R`); a rung within `snap_tol_atr * ATR` of a structural level
is snapped onto it and its `src` records the structure (`pivot` / `donchian`),
otherwise `src="atr"`. `trail_stop()` is the ratchet-only ATR trail
(`trail_atr`, activation at `trail_activate_r`).

`LevelsConfig` defaults mirror the Phase 1 brief: `atr_len=14`,
`fractal_width=2`, `cluster_atr=0.5`, `donchian_len=20`, `k_base=1.5`,
`k_regime_bounds=(0.75, 1.5)`, `rr_floor=1.5`, `tp_rmultiples=(1, 2, 3)`,
`trail_atr=2.0`.

**JSON contract** (`levels_api.py`): `{pair, direction, entry{low,high,ref},
sl, tp_ladder[{r,price,src}], trail_policy, source_ref, computed_at}` plus the
diagnostic scalars `atr`, `k_eff`, `regime`, `branch`, `pivot_count`, `asof`
and `reward_uncapped` (`true` = no opposite structure, so the structural stop
was accepted without a bounded R:R check — uncapped upside by design).
Values are the raw engine floats — deliberately **not** passed through
`_utils.safe_float`, which would round to 4dp.

**`source_ref` grammar:** `computed:atr14@<asof>|k=<k_eff>|reg=<regime>|br=atr|pivot|donchian|piv=<fractal_width>|rr=<rr_floor>|src=base`.
The `computed:` prefix is shared with the twelve-x dashboard label, which is
extended to parse `atr` in the Track E follow-on (the engine does not rename
the prefix). No writes, sizing or order placement anywhere in this path — the
existing twelve-x `apply_guard` remains the final authority on published levels.

`digiquant_get_trade_levels` exposes the engine on both the MCP (READ scope)
and orchestrator manifest surfaces; see the MCP tools table above. The
NautilusTrader parity harness is described in
[docs/NAUTILUS_NAVIGATION.md](../NAUTILUS_NAVIGATION.md).

### Macro-liquidity regime gauge (#1085)

`indicators/macro_liquidity.py` expands the M2-only vote in
`indicators/m2_signals.py` into a pluggable **macro-liquidity regime model**
for downstream gates (RS rotation #1084, active books, composition #1078).

| Piece | Role |
|---|---|
| `MacroSeriesSpec` | Pluggable vote: `name`, FRED `series_id`, `weight`, `sign` (±1), `transform` (`level` / `yoy` / `roc`) |
| `MacroLiquidityConfig` | Rolling window + expansion/contraction score thresholds + specs tuple |
| `MacroLiquidityModel.compute` | Align → transform → causal rolling-z → signed blend + equal-weight 0/1 vote → `regime_score` [0,100], `regime_state`, `risk_on` |
| `write_regime_series` / `load_regime_series` / `regime_index_by_date` | Consumer surface (parquet + date map) — no Nautilus dependency |
| `backtest_regime_gate` | CI-only long-vs-cash harness documenting gated vs always-invested returns — **not** a published `BacktestResult` |

**Default blend** (equal weights): `M2SL` YoY (+), `UNRATE` level (−). The `DTWEXBGS` (dollar) and `MANEMP` (manufacturing-activity / PMI proxy) votes were removed 2026-09-29: neither is served by the anonymous gloomberb panel, so `MacroSeriesSpec`s for them still work but only for callers supplying their own frames. Score map: `regime_score = 50 + composite_z × 50/3` (100 = max expansion). Discrete: `expansion` if score ≥ 60, `contraction` if ≤ 40, else `neutral`. `risk_on` is true only in expansion (gate open); neutral/contraction raise cash in the CI gate harness.

**Data path.** Series land via the existing macro pipeline
(`digiquant prices fetch-macro` → `macro_series_observations`). Manifest
`research/config/macro_series.yaml` lists `M2SL` and `UNRATE` from the panel —
no hardcoded secrets. Callers pass already-fetched
`{name: DataFrame[date, value]}` into `compute`; the model never fetches.

**Consumers.** Other strategies read the regime parquet / `regime_index_by_date`
map. `M2LiquidityStrategy` stays the M2-ROC Nautilus book; it is not rewritten
here. Weight/window tuning belongs to the optimization engine (#1079).

**Gate backtest (documented effect).** On a synthetic rise-then-crash path with
`risk_on` true only on the rising half, `backtest_regime_gate` shows
`gated_return_pct > always_in_return_pct` (cash through the drawdown). Unit
pin: `tests/dq/indicators/test_macro_liquidity.py`. Run
`pytest -m unit -k "macro or liquidity or m2"`.

### Relative-strength asset rotation (#1084)

Phase-0 design note: [`docs/research/rs-rotation-v1.md`](../../../docs/research/rs-rotation-v1.md)
(dual momentum + risk-adjusted cross-sectional rank; weekly rebalance; cash when
no absolute-strength qualifier).

| Piece | Role |
|---|---|
| `indicators/rs_ranker.py` (`RsRanker`) | Pool → per-asset absolute return, vol, risk-adj score, cross-sectional `rs_rank` (1=strongest), `qualifies` (abs return > threshold). Shared RS signal for SDCA #1082 / composition #1078. |
| `strategies/rotation/backtest.py` | CI-only long-only top-N rotator vs equal-weight + buy-&-hold — **not** a published `BacktestResult`. Absolute gate → cash; optional `#1085` `risk_on` overlay forces cash when false/null. |
| `strategies/rotation/nautilus_strategy.py` | Nautilus long-only rotator: loads `date,symbol,weight` parquet (precompute → drive, same pattern as `m2_liquidity` / SDCA). Registered as `rs_rotation`. |

**v1 defaults.** Lookback 90 / skip ≥1 (default 7) / absolute threshold 0 / top-N 1 / rebalance every 7 days. Phase 2+ (long/short, spreads, vol targeting, correlation-aware pool, default-on regime gate) stays deferred. Window/weight search belongs to #1079. No live-trading; no `--push-supabase`.

**Tests.** `pytest -m unit -k "rotation or rs"` (ranker + rotation harness + Nautilus config when installed).

### Gloomberb market-data client (#4069, expanded by #4110 phase 1)

`data/gloomberb/` is the digifetch × Gloomberb data layer (spec:
[`2026-09-12-digifetch-scoping-design.md`](../../../docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md),
approach (c)). It is a Python HTTP client over `https://api.gloom.sh` built on
the `digifetch` transport engine — `digifetch` stays generic (no URLs, no site
logic, no env reads) and the site logic lives here:

| Module | Responsibility |
|--------|----------------|
| `data/gloomberb/models.py` | Pydantic v2 input/output models for the 89 tools, the shared `DigifetchEnvelope[T]`/`DigifetchError` contract, the §5.2 resolution × range caps (reject, never clamp), and the #4100 explicit date window (`start_date`/`end_date`, mutually exclusive with `range`) |
| `data/gloomberb/normalizers.py` | Ported §5.4 normalizers: GBp/GBX→GBP divisor, interval tokens, exchange-timezone bar dates, malformed-intraday rejection, day-range reconciliation, and the §5.3 freshness union (wire `stale` vs `dataSource`/`delayMinutes`) |
| `data/gloomberb/client.py` | `GloomberbClient` on `digifetch.HttpFetcher`/`RateLimiter`/`with_retry`: endpoint map, wire→error mapping, 900s TTL cache, circuit breaker (half-open probe), kill switch, optional session cookie, Yahoo/yfinance earnings path |
| `data/gloomberb/attribution.py` | §7 attribution: "Sourced from Gloomberb", delay notice, `term.gloom.sh/?ticker=` deep links |

**Envelope and errors.** Every call returns the same envelope —
`{source, provider_id, fetched_at, stale, delay_note, warnings, data}` — where
`data` is the success payload or a typed `DigifetchError{code, message,
retryable}`. Codes: `auth_required` (401/403, or a gated route with no session
cookie — no request is made), `pro_required` (a valid session without a
Gloomberb Pro entitlement; see Entitlements below), `not_found` (404, envelope
`empty`/`unsupported`), `rate_limited` (429, `Retry-After` echoed),
`upstream_error` (5xx/timeout/`retryable_error`/`fatal_error`), `invalid_input`
(Pydantic input failure). Tools never raise to the transport.

**Freshness.** Wire `stale: true` — on the response envelope, `providerMeta`, or
the payload itself (e.g. a quote's `data.stale`, spec §3.2) — maps to
`stale=true` + `"Upstream cache stale"`; the free-tier delay
(`dataSource: "delayed"` or `delayMinutes > 0`) maps to
`"Free-tier data delayed up to 15 minutes"` with `stale=false`. Both signals
stay distinct.

**Pacing and safety.** The client is default-OFF behind `GLOOMBERB_ENABLED`; an explicit opt-in (``1``/``true``/``yes``/``on``) re-enables it; only
`1`/`true`/`yes`/`on` enable it, and any other value (a typo included) fails
closed to disabled (see Environment Variables). A 900s TTL cache matches the R2
market-data-cache convention; expired entries are evicted on access and the
cache is size-bounded, so a long-lived process cannot grow without limit. The
cache key includes a **non-reversible session fingerprint** (a truncated
SHA-256 of the cookie, or `"anon"`) because responses are
entitlement-sensitive — a preview or Pro report cached by one session is never
served to a different session, and the raw cookie never enters the key (#4110
phase 5). A `RateLimiter` min-interval gate paces requests; the retry policy is narrowed to
timeouts/connection faults and wire 5xx so 401/404/429 are never retried; a 429
`Retry-After` is honored with a bounded injectable sleep (a larger value is
surfaced in the typed error, not slept on). Only upstream-health failures
(transport errors, 5xx, 429, envelope `retryable_error`/`fatal_error`) count
toward the circuit breaker — deterministic 4xx outcomes such as `auth_required`
never open it. N consecutive failures open the breaker, which fails fast to a
typed `upstream_error` with a half-open probe after the reset window.
`GLOOMBERB_SESSION_COOKIE` is attached only to the 41 cookie-gated tools
(37 `session` + 1 `preview` + 3 `pro`, declared once in
`data/gloomberb/entitlements.py`): the original nine reads (holders, analyst
research, corporate actions, research search, statements, ticker tweets, tweet
search, short interest, saved searches) plus equity diagnostic (preview) and
transcripts/screener/options-flow (pro), the 15 probe-backed Cloud reads, and
the 13 inert workspace/broker tools (`digifetch_substack` instead needs its
own `SUBSTACK_SESSION_COOKIE`). It is never logged, never appears in tool
payloads, and is forwarded only to same-origin redirect hops. The
`/public/proxies/*`, `/public/risks/*`, and `/public/events/*` filing reads are
open (no account, no cookie). Plan-gated routes are detected from the response
body: a `Pro plan required` answer (JSON or text, any status) or a 200
`status=unsupported` + `reasonCode=PRO_REQUIRED` envelope both map to a typed
`pro_required` — never a generic non-JSON `upstream_error`, a `not_found`, an
`auth_required`, or an empty success — and neither shape trips the breaker.
A bare 402 without a recognizable plan body keeps the generic
`auth_required` mapping, and a gated route with no cookie at all still
short-circuits to `auth_required` before any HTTP call.

**Entitlements (#4110 phase 5).** Every digifetch tool declares one entitlement
in [`data/gloomberb/entitlements.py`](../../src/digiquant/data/gloomberb/entitlements.py)
(`TOOL_ENTITLEMENTS`), and that one declaration is surfaced in three places:
the MCP registration (`_maybe_tool` sets `fn.entitlement` and appends the note
to the registered description), the orchestrator manifest (a top-level
`entitlement` key plus the same description note), and therefore the tool
descriptions an agent reads. Vocabulary:

| Entitlement | Meaning | Tools |
|-------------|---------|-------|
| `free` | Anonymous read; no session cookie needed | `digifetch_quote`, `quotes_batch`, `price_history`, `ticker_financials`, `options_chain`, `sec_filings`, `earnings_calendar`, `exchange_rate`, `search`, `news`, `econ_calendar`, `econ_series`, `yield_curve`, `cds`, `congress_trades`†, `venues`, `13f_funds`, `13f_holdings`, `shiller`, `proxy_statements`, `filing_events`, `risk_reports` |
| `session` | `GLOOMBERB_SESSION_COOKIE` required; without it `auth_required` with **no HTTP request** | `digifetch_holders`, `analyst_research`, `corporate_actions`, `research_search`, `statements`, `ticker_tweets`, `tweet_search`, `short_interest`, `saved_searches` |
| `preview` | Session required; a free (email-verified) session still gets a labeled preview | `digifetch_equity_diagnostic` |
| `pro` | Session **and** a Gloomberb Pro plan; a free session is gated with `pro_required` | `digifetch_transcripts`, `digifetch_screener` |

† `digifetch_congress_trades` keeps its `free` entitlement declaration so the
client and normalizer stay coherent if Counsel clears the refusal, but it is
**refused on every surface** and is not reachable — see the refusal list below.

**Refused tools (DIG-1057).** `digiquant.tool_refusals` holds a deny-by-default
`REFUSED_TOOLS` frozenset — currently `{"digifetch_congress_trades"}` — naming
tools Counsel has ruled we must not obtain or serve, currently under 5 U.S.C.
13107(c)(1)(B) (no House/Senate disclosure report for a commercial purpose other
than news-and-communications-media dissemination). A refused tool is enforced in
three places, so it cannot be reached by any route that matters:

- `mcp_server._maybe_tool` returns without registering, so the name is absent
  from `create_mcp_server(scope="read")` **and** `scope="full"` — it is not
  merely dropped from `READ_SCOPE_TOOLS`;
- `build_orchestrator_tool_manifest()` filters refused names out of the
  `POST /v1/orchestrator_tools` manifest, so no schema advertises it;
- `server.v1_orchestrator_invoke` answers a typed
  `{"ok": false, "refused": true, "code": "tool_refused", …}` envelope **before**
  any dispatch branch, so the HTTP invoke path cannot reach the upstream even
  though `DIGIFETCH_DISPATCH` still carries the name.

The refusal is deliberately *registration-level*, not deletion: the Gloomberb
client method, the normalizer, the Pydantic models and the entitlement entry all
stay in-tree so a clearance is a one-line removal from the frozenset rather than
a re-derivation of the endpoint shape. Tests pin all four properties: absent from
both scopes, absent from the manifest, typed refusal from the invoke route, and
the client `ENDPOINTS` entry still present.

**The refusal env denylist is additive only (DIG-1251 Q5).** Counsel approved the
env-deny-only shape on condition that it can never *permit* a refused feed, so the
effective rule is a union:

```text
refused = REFUSED_TOOLS ∪ env_denied_tools(DIGIQUANT_REFUSED_TOOLS)
```

`DIGIQUANT_REFUSED_TOOLS` is a separator-delimited list (`,`, `;` or whitespace) of
extra tool names, read per call so a deployment change applies on the next
request. Three properties make condition 1 structural rather than aspirational:
`REFUSED_TOOLS` membership short-circuits before the variable is consulted; the
parser has **no allow / negate / un-refuse syntax**, so `-name`, `!name` and
`allow=name` are unknown tokens rather than permissions; and case-folding can only
match more names. Missing, empty or whitespace-only contributes no names, leaving
the code constant in force (fail closed), and a malformed value yields tokens
rather than raising past the refusal check.

The code constant stays the carrier of `digifetch_congress_trades`: an env var is
not a legal gate, and the real gate is Counsel's written clearance plus the CTO's
merge. `tests/dq/test_tool_refusals_env_denylist.py` proves it rather than logging
it — every `REFUSED_TOOLS` member stays refused under every legal value of the
variable, *and* the variable demonstrably adds refusals, so an implementation that
ignored the environment entirely could not pass.

Note for readers: the three `luxalgo_trackers_*` tools are **not** in
`REFUSED_TOOLS`. Their absence is not a clearance — see DIG-1251.

`pro_required` is distinct from `auth_required` on purpose: `auth_required`
means no/misconfigured session (fix `GLOOMBERB_SESSION_COOKIE`), while
`pro_required` means the session is valid but not entitled (upgrade the
account, or wait for the DigiQuant bundling below). It is always
non-retryable and never counts toward the circuit breaker — both live gate
shapes (402/plan-required text or JSON body, and the 200
`PRO_REQUIRED` envelope) are deterministic outcomes, not degradation. A Pro
session is supplied by putting a **Gloomberb Pro account's** cookie in
`GLOOMBERB_SESSION_COOKIE` (bare token or `name=value`); digiquant has no
separate Pro switch.

Preview surfacing: when the equity diagnostic returns `access="preview"` the
envelope carries the machine-matchable warning
`preview access: report is a free-tier preview (access=preview)`
(`PREVIEW_ACCESS_WARNING`), and `data.report.access` stays the canonical
passthrough field. Full reports carry neither the warning nor a marker.

**DigiQuant bundling (placeholder, not implemented).** DigiQuant's highest
subscription tier may bundle Gloomberb Pro access in the future — a
business/partnership follow-up, not a code path in this phase. The
`entitlement="pro"` declaration is the hook a bundling layer would resolve
against (e.g. a future tier→entitlement map); **no billing or entitlement
upgrade code exists here**, and `GLOOMBERB_SESSION_COOKIE` remains the only
way to supply a Pro session today.

**Exposure.** All 89 tools are registered in `mcp_server.py` via the
`_maybe_tool` pattern (read scope) and in the `orchestrator_tools.py` manifest.
The lazily-cached `_build_gloomberb_client()` seam is keyed on the kill-switch +
cookie env pair, so tests inject a `MockTransport`-backed client and an env
change gets a fresh client. Attribution/deep links are appended by
`_gloomberb_envelope_json`; 39 tools pass `attributed=False` and opt out of the
top-level "Sourced from Gloomberb" claim and the term.gloom.sh link: the six
Task 2 calculators/compositions plus `digifetch_options_scenario` and the ten
Task 3 portfolio-math compositions (derived math, never Cloud-sourced — their
attribution, if any, lives inside `data`), the venue-direct readers
(`digifetch_prediction_markets`, the five Task 6 ToS tools, `digifetch_trending`,
`digifetch_substack`), the Yahoo-backed `digifetch_earnings_calendar`, and the
13 write-shaped Task 7 workspace/broker tools (inert posture payloads, nothing
to attribute).

**Coverage expansion (#4110 phase 1).** Seven read tools joined the family on
the same envelope/attribution/pacing semantics: `digifetch_econ_calendar`
(parameterless — the route returns a fixed ~105-row window and ignores
`limit`), `digifetch_econ_series` (FRED-style observations; a missing `info`
maps to null), `digifetch_yield_curve`, `digifetch_cds` (DTCC PPD; `days`
validated 1–90 client-side), and the session-gated
`digifetch_research_search` (401/402 → `auth_required`; `offset` + a typed
pagination block) and `digifetch_transcripts` (requires Gloomberb Pro; the
live 402 `Pro plan required` body → `pro_required`; rows live under the
upstream `calls` key). `digifetch_congress_trades` is **refused on every surface** — see the
refusal-list section below; it is not registered in any MCP scope, filtered out
of the manifest, and typed-refused by `v1_orchestrator_invoke`. Its upstream is
live (probed 2026-10-05: HTTP 200, `source: "house-clerk"`, `filingCount: 407`,
`filingsParsed: 20`), which is why it is refused rather than left inert. Its
client, normalizer and models are retained in-tree for a possible Counsel
clearance. While it was live its typed subset followed the known field names
(`memberName`/`assetName`/`sourceUrl`/`filingDate`/`notificationDate`)
and the rest is preserved. These routes answer direct payloads (bare arrays
included) rather than the `/market/*` envelope, so `_request_json` takes
`allow_array` for them; array rows' `stale` flags fold into the envelope via
the existing freshness helper. Wire types for the partly-probed routes are
deliberately permissive (`float | str`, `str | int`) so a textual print does
not fail validation. Because these `/cloud/*` payloads carry no
`dataSource`/`delayMinutes`, `delay_note` stays null for them — the
platform-wide delay is stated in the tool descriptions instead.

**Coverage expansion (#4110 phase 2).** Seven more read tools joined on the
same semantics: `digifetch_statements` (session-gated; sparse statement rows,
extras keep the long tail), `digifetch_ticker_tweets` and
`digifetch_tweet_search` (session-gated; the upstream echoes `limit`/`hours`
but applies neither, so the client drops rows older than `now - hours` when
`hours` is given, slices to `limit`, and reports `total_available`/`truncated`),
`digifetch_venues` (anonymous; 137 venue rows),
`digifetch_screener` (session-gated, **Pro-only** — both the 200
`PRO_REQUIRED` envelope and the 402 text body map to the same non-retryable
`pro_required`; the Pro success payload is unobservable, so rows are typed from the
TS plugin's `CloudMarketScreenerItem` with every field optional),
and the two 13F tools (`digifetch_13f_funds` for fund search/top/ticker
map/CUSIP holders, `digifetch_13f_holdings` for filings/forms/one form's
holdings; anonymous; `cik` zero-padded to 10 digits and `accession_number`
normalized to the dashed form; holding rows mapped to
`issuer`/`shares`/`share_type`; `has_more` computed from a full page because the
upstream answers a bare array). An upstream 13F rejection proxied as a 5xx with
a `Forms13F 4xx` body is detected in the transport attempt and mapped to
non-retryable `invalid_input` without retrying or recording a breaker failure.
The 13F `holders`, `funds` and `topfunds`
routes were probed live; `holders` currently answers a proxied 4xx for every
period format probed, so it is exposed against the documented shape and noted
here. The same `delay_note`-is-null caveat applies: state the platform-wide
delay in descriptions, never promise `data.delay_note`.

**Coverage expansion (#4110 phase 3).** Six more read tools joined, closing the
plugin-only panes that had a real Cloud/API endpoint: `digifetch_shiller` (the
monthly valuation series behind the market-valuation pane; a client-side tail
slice with `total_available`/`truncated`), `digifetch_proxy_statements` and
`digifetch_risk_reports` (the executives and risk-factors panes, served by the
anonymous **`/public/proxies`** and **`/public/risks`** open reads — list +
per-year detail, `what`-discriminated), `digifetch_filing_events` (the
filing-events pane's classified 8-K feed), `digifetch_short_interest`
(session-gated `/market/short-interest`, `years` 1–10 client-side), and
`digifetch_equity_diagnostic` (the research pane's POST
`/research/equity-diagnostic` AI review; pending-or-report union, no pending
caching, `direct_payload` because its own `status` field collides with the
market envelope, `access=preview` for free sessions). Live-probed 2026-09-15
with the repo session cookie; the public filing routes need no cookie at all.

**Coverage expansion (#4110 phase 4a).** The two residual endpoints now ship:
`digifetch_transcripts` folds in its detail route as a `transcript_id` mode
(`GET /cloud/transcripts/{id}`; exactly one of `ticker`/`transcript_id`,
Pro/session semantics unchanged), and the new parameterless, session-gated
`digifetch_saved_searches` covers `GET /cloud/search/saved`. Both were
probed live 2026-09-16 with a free session: the saved-searches route answered
`200 {"searches": []}` (so the entitlement is `session`, not `pro`) while both
transcript routes answered the free-session `402 Pro plan required`, leaving the
transcript detail row shape **probe-pending** (the models stay permissive) until
a Pro-account probe re-records it. The `saved`-key fallback is retained as an
unverified variant.

**Prediction markets (#4813).** `digifetch_prediction_markets` is the
family's first venue-direct tool: no Cloud route exists, so the client reads
the Polymarket Gamma `/events` catalog and the Kalshi trade `/events` catalog
straight through the shared digifetch transport (`_request_json` takes a
`base_url` + `label` so venue calls share pacing/retry/breaker with
venue-named errors; a venue 401/402/403 maps to `upstream_error`, never to the
session-cookie `auth_required`). Only `limit` (plus Kalshi's `open` status) is
sent upstream — the venues' search/category/tab parameters are unprobed, so
`query`/`category`/`tab` filter client-side and `limit` (1–100) slices the
merged rows. Gamma's JSON-encoded `outcomes`/`outcomePrices` resolve the Yes
probability; Kalshi's dollar-or-cent prices scale by 100 when above 1. Each
venue fails soft into the result `warnings`; all-requested-venues-down is a
typed `upstream_error`. Rows carry the venue deep link
(`polymarket.com/event/{slug}`, `kalshi.com/markets/{ticker}`); the envelope
`provider_id` is `prediction-markets-venues`, the result attribution names the
venues with a polling notice, and both surfaces pass `attributed=False`, so no
top-level attribution or term.gloom.sh link is ever emitted. Entitlement is
`free`; the tool joins `MACRO_TOOLS` only (now at the 16-name prompt-budget
cap; subsets stay distinct). Not live-probed: venue shapes are parsed
defensively from the plugin's documented reads, and the offline suite drives
both venues through `MockTransport`.

**Full-function coverage (#4837).** All 130 command-bar functions now carry
exactly one status in the
[function matrix](../../../docs/superpowers/plans/2026-09-30-gloomberb-function-matrix.md):
57 DONE, 24 COMP, 4 CALC, 1 TOS, 11 WRITE, 2 GATE, 1 NATIVE
(`digiquant_run_backtest` — no gloomberb tool), and 30 OUT. New cohorts since
#4813: calculators + compositions (`digifetch_options_calculator`,
`digifetch_bond_calculator`, `digifetch_kelly_sizer`, `digifetch_dividend_yield`,
`digifetch_fx_cross_rates`, `digifetch_vix_term_structure` — the kelly-sizer is
no longer "a local model with no data endpoint", it is a shipped tool);
portfolio-math compositions (`digifetch_compare_performance`,
`digifetch_correlation_matrix`, `digifetch_relationship_graph`,
`digifetch_relative_valuation`, `digifetch_fundamental_graph`,
`digifetch_valuation_graph`, `digifetch_custom_chart`,
`digifetch_market_valuation`, `digifetch_money_markets`,
`digifetch_rate_path`); the options-scenario composer
(`digifetch_options_scenario`, multi-leg valuation over options-chain rows);
probe-backed Cloud reads (`digifetch_time_and_sales`,
`digifetch_quote_recap`, `digifetch_estimate_revisions`,
`digifetch_short_volume`, `digifetch_hiring`,
`digifetch_central_bank_rates`, `digifetch_cdx`,
`digifetch_sovereign_cds`, `digifetch_options_flow`, `digifetch_cot`,
`digifetch_crypto_markets`, `digifetch_iv_screen`, `digifetch_iv_history`,
`digifetch_iv_surface`, `digifetch_debt_maturities`,
`digifetch_session_movers`, `digifetch_trending`, `digifetch_substack`,
`digifetch_ipo_calendar`); venue-direct ToS readers (`digifetch_fear_greed`,
`digifetch_polls`, `digifetch_treasury_auctions`, `digifetch_market_halts`,
`digifetch_hacker_news`); and the session-gated workspace/broker cohort, which
is inert by verdict (below). The curated subsets sit at their 16-name
prompt-budget caps (EQUITY/MACRO/PM 16/16/16); `digifetch_polls`, `digifetch_hacker_news`, `digifetch_compare_performance`,
`digifetch_correlation_matrix`, and `digifetch_relative_valuation` stay
MCP-only until an owner-signed eviction frees a slot;
`digifetch_congress_trades` is on none of them at all — it is refused
(DIG-1057, 5 U.S.C. 13107(c)(1)(B)) and must not be added back to a subset
without Counsel's written clearance.

**Composition behaviors worth knowing.** `digifetch_dividend_yield` inherits the
`corporate_actions` session gate without a cookie: both legs are attempted, the
gate failure lands in `warnings`, and the tool answers a typed
`upstream_error`, never a partial yield. The IV-history entitlement is a guess
pending live smoke: the IV trio stays `session` with `pro_gated` readers, so a
server plan denial surfaces verbatim as `pro_required`. The VIX far leg
defaults to the FRED id `VXVCLS` — `VIX3M` as such is the Yahoo/CBOE index
symbol `^VIX3M`, not a FRED id. `digifetch_rate_path` reads a single page of
open Kalshi `KXFED` threshold markets and groups by meeting. The 13
write-shaped workspace/broker tools are inert and read-only in this phase (no
personal Cloud write route verified — the 2026-09-30 source probe found only
team-scoped account APIs): without a cookie they answer `auth_required` with
zero HTTP, with one they answer the typed read-only `upstream_error`, also with
zero HTTP. `digifetch_ibkr_preview_order` mints a local HMAC approval ticket
(single-use, 15-minute TTL); `digifetch_ibkr_execute_order` ships DISABLED
pending human review of the approval-gate design — only `dry_run` returns data
(the would-be request, zero brokerage traffic). Enablement additionally
requires the order exchange to match a pre-enabled local-gateway venue: orders
route through the local IBKR gateway, never Cloud REST.

**Deliberately out of scope (the 30 OUT rows).** No data endpoint exists for the
AI surfaces (`AI` BYOK key, `AGENT` BYOK key, `ASKG` Cloud AI chat), the live
video pane (`TV`), the account surfaces (`CHAT`, `DM`, `TEAM`, `FOCUS`, `TBO`,
`ACM`, `UPGRADE`), or the 16 layout/settings panes (`GL`, `LAY`, `LMA`, `WIN`,
`PS`, `PL`, `TH`, `LANG`, `FONT`, `SB`, `VF`, `CR`, `CONN`, `CHG`, `HELP`, `FB`
— app chrome, no API surface). `FUT`/`CTM` stay on Yahoo continuous symbols by
prior decision. `HILO` is a socket-only streaming scanner with no REST
equivalent and no tool-shaped equivalent; 52-week extremes already surface in
quotes/screener. The single sanctioned split is `MOST`: gainers/losers/most-active
via `digifetch_screener`, premarket/afterhours/gaps via
`digifetch_session_movers`, trending via the Yahoo venue-direct
`digifetch_trending`. NO-ROUTE verdicts compose over tooled routes without a
dedicated endpoint (`HVG`/`HVT` realized-vol over price history + options-chain
ATM overlay, `EE` over corporate actions + analyst research + financials, `INS`
over SEC Form 4 content, `CRD` over econ-series FRED credit ids); `GUID`
harvests guidance quotes from transcripts text, labeled as such. The
per-transcript detail route (`/cloud/transcripts/{id}`) shipped as
`digifetch_transcripts`' `transcript_id` mode (#4110 phase 4a);
`digifetch_saved_searches` covers `/cloud/search/saved`.

**Not a pipeline primary.** The 15-minute free-tier delay, rate limits, and
`1wk→5y` range cap disqualify the Cloud surface as a primary data source. It
enriches dashboard/chat reads only (the #4100 date window widens history reads
past that cap, but the delay and rate limits are unchanged).
`digifetch_earnings_calendar` follows
digiquant's existing `yfinance` dependency (same Yahoo upstream); the Cloud
client does not own it unless a Cloud route appears.

### Optimization Engine Selection

The dispatch in `run_optimize()`:

1. If the resolved strategy name is `sdca` (alias `btc_sdca`), run
   `run_sdca_walk_forward()` with the Nautilus evaluator. The slapper
   Sharpe/return path is not used. Objective is **maximize
   `vs_flat_dca_pct`** subject to `capital_deployed_pct >= 10` and
   `max_drawdown_pct <= 50` (magnitudes, ×100). `vs_lump_pct` is reported
   never optimized — maximizing it collapses to lump-sum on an uptrend.
   Auto-grid holds `buy_curvature`/`sell_curvature` and extra-indicator
   weights at defaults (valuation=1, extras=0; 2-point grid on the remaining
   shape params). `method=random`/`bayesian` samples shape plus all extra
   weights, including
   `m2_weight` / `rs_eth_weight` / `dxy_weight` /
   `weekly_rsi_weight` / `weekly_macd_weight` / `sma_band_weight` in `[0, 1]`
   (the composite already normalizes by `Σ w`). Rails are refit per fold on
   the IS window only. Extra-z is causal on the full calendar, then sliced.
2. If `param_grid` is provided explicitly, skip method inference and run that grid directly
3. If `method == "bayesian"`, delegate to `run_optimize_bayesian()` (Optuna)
4. If `method == "random"`, call `sample_random_params()` then `_run_trials_parallel()`
5. Otherwise (grid default), call `infer_param_grid()` then `_run_trials_parallel()`

`infer_param_grid()` reads from `STRATEGY_PARAM_SPECS` in `strategy_specs.py`, which can be extended at runtime via a YAML file pointed to by `DIGIQUANT_STRATEGY_SPECS_PATH`. A hard cap of `MAX_GRID_SIZE = 10_000` prevents combinatorial explosion.

`_run_trials_parallel()` uses `ProcessPoolExecutor` for grid and random methods. It falls back to sequential execution if the executor raises (common on macOS due to `spawn` context restrictions). When `max_workers=1`, the parallel path is skipped and execution is sequential.

### Audit JSONL Flow

`digiquant.audit.audit_log` is a thin wrapper over `digibase.audit.emit_event`
(CHR-151 / #1193). The digibase emitter appends one JSON line per event to
`AUDIT_LOG_PATH` (default: `digiquant/results/audit/events.jsonl`). Each event
matches the Pydantic `AuditEvent` schema: `ts`, `event_type`, `agent_id`,
`payload`, and optional `key_prefix`, `tenant`, `project_id`, `jti`, `path`.

Before writing, `emit_event` redacts any payload key containing `password`,
`api_key`, `token`, or `secret` (case-insensitive substring match, recursive into
nested dicts/lists). The file is opened in append mode on every call; there is
no buffering or rotation mechanism.

Audit events are written explicitly in `server.py` after `run_backtest`,
`run_optimize`, pipeline, and `v1_workflow`. The `run_export` synchronous
endpoint does not write an audit event.

---

