# Gold live-path work order (Plan 10 Task 3 — document only, no code)

Status: **WRITE-UP ONLY.** Nothing below is decided and nothing below is
implemented. Each §2 decision ends with an OPEN question, not an answer.
Authoring any code, settings, workflow, or fetcher edit from this note without
a fresh owner-scoped plan fails review.

Context: gold v3 winner (`gold_optimized` preset, shape 35/45/50/30/1.0/2.0,
weights valuation 1.0 / m2 0.5 / uup 0.5) scored its single holdout
(2022-05-12..2026-09-29) at **−21.16% vs flat DCA, feasible** (peak-deployed
~100%, dd 8.65). Promotion artifacts (`gold_optimized`, `gold_sdca`,
`gold_optimized_provenance.json`) sit branch-only, unmerged, unpushed. The
nightly/live path still assumes BTC. This note scopes its generalization.

All file:line references re-verified by reading on branch
`task/4804-sdca-strategy-for-gold--gld` (tip `1a59bdafe`) at work-order time.
Line numbers will drift; symbol names are the stable handle.

## 1. Problem

The SDCA branch of `digiquant/scripts/generate_tearsheets.py` is BTC-hardcoded
in four sites (recon §4, re-verified). A `gold_sdca` tearsheet off today's code
either fails loud (registry) or — worse — publishes a silently BTC-shaped
index. Task 2's live-branch read additionally found the registry gap (§1.5).

### Site 1 — weights block (`generate_tearsheets.py:792-801`)

The branch reads `sdca_cfg.get("indicator_weights")` but constructs only seven
keys (`valuation`, `m2`, `rs_eth`, `dxy`, `weekly_rsi`, `weekly_macd`,
`sma_band`; `:793-801`). The catalog model `SdcaCompositeWeights`
(`strategies/sdca/indicator_catalog.py:120-…`) already carries `uup` (`:129`)
plus the gold macro keys (`gvz`, `walcl`, `hy_oas`, `ig_oas`,
`breakeven_5y`, `nfci`, …) — and the `gold_sdca` settings entry ships a full
16-key map including `uup: 0.5`. Everything outside the seven is silently
dropped before the index is built. The `extra_weights` / `extras_unused`
tuple (`:843-851`) repeats the same seven-key horizon, so the provenance note
would also misreport a gold run as "power-law only".

### Site 2 — drop-guard report (`generate_tearsheets.py:812-818`)

The library function `drop_extras_missing_sources` (`strategies/sdca/optimize.py:244-274`)
already generalizes: it zeroes `uup`, `gvz`, `walcl`, `hy_oas`, `ig_oas`,
`breakeven_5y`, `nfci`, `gdx_gld`, `gld_slv` when their source series is
absent. But the caller's `dropped_this_run` report list (`:814-818`) names only
`("m2", "dxy", "rs_eth")`. Combined with Site 1, a missing UUP series at
nightly runtime would be zeroed inside a weights object that never contained it
— no provenance trace that the uup 0.5 leg went dark.

### Site 3 — risk model (`generate_tearsheets.py:161-168` + `:834`)

`materialize_sdca_risk_index` (`:150-177`) hardcodes
`BtcPowerLawRiskModel(load_coefficients(...))` at `:168`, and the SDCA branch
loads BTC rails coefficients at `:834` (`coefficients = load_coefficients()`).
The `gold_sdca` settings entry declares `risk_model: generic_valuation`; the
branch prints `risk_model=` into provenance (`:855`) but never dispatches on
it. A dispatcher exists and is unused here: `resolve_sdca_risk_model`
(`strategies/sdca/providers.py:48`), serving `btc_power_law` /
`generic_valuation` / `rolling_z` (names at `:40-46`).

### Site 4 — provenance (`generate_tearsheets.py:852-859`, adjacent `:808-820`)

The risk-index provenance note (`:852-859`) prints the same seven weights as
Site 1. Adjacent at `:808` / `:820` the branch imports and probe-calls
`load_btc_optimized_provenance()` — BTC-specific; there is no gold (or generic)
provenance loader on this path.

### §1.5 Task-2-observed (not recon): registry (`nautilus_strategy.py:360-361`)

Only `btc_sdca` is Nautilus-registered. `get_strategy("gold_sdca")` fails at
resolution — loud, which is the good failure mode, but it means no gold
tearsheet runs at all until registration plus Sites 1–4 are addressed together.
Registration alone without Sites 1–4 would flip the failure from loud to
silent (a published valuation-only BTC-rails index under a gold label).

## 2. Decisions NEEDED (options with trade-offs — none made)

### D1 — GLD price source for nightly

The nightly fetcher `digiquant/scripts/fetch_coinbase.py` serves exactly three
symbols (`SYMBOLS`, `:28-32`: BTC/USD, ETH/USD, SOL/USD). GLD-USD.csv is not
fetched; the v3 seed bars came from the research path, not the nightly path.
Three options, stated without recommendation:

- **(a) R2 sealed `market-data/price/GLD` generations.** Layout exists:
  `market-data/price/{TICKER}/{as_of}.parquet` plus `…/latest`
  (`data/prices/r2_history.py:39,52-58`). Trade-offs: sealed, versioned,
  replayable — matches the provenance story; but requires a writer that seals
  GLD generations on schedule (no such writer verified), and the nightly job
  currently reads `digiquant/data/price-history` CSVs, not R2 keys, so a reader
  shim or staging step is implied, not free.
- **(b) Extend `fetch_coinbase` with a GLD pair.** Trade-offs: smallest diff,
  rides the existing nightly step (`pipeline-digiquant-tearsheets.yml:71`) and
  the `history_cache`/`load_cached` reader the branch already uses (`:738-742`);
  but GLD is not a Coinbase spot pair in any verified listing — venue
  availability is assumed, not established — and stuffing a non-crypto series
  into a crypto fetcher may be the wrong home for it.
- **(c) Yahoo (or equivalent equities quote source).** Trade-offs: GLD natively
  lives there; the repo already treats Yahoo as a price boundary
  (`data/prices/fetchers.py` pandas boundary, per digiquant AGENTS allowlist);
  but rate limits are a known hazard, the nightly pipeline has no Yahoo staging
  step today, and cache naming/ticker conventions (`GLD-USD.csv` vs Yahoo
  symbols) need pinning.

**OPEN: which of (a)/(b)/(c) — or a combination — supplies GLD-USD bars to the
nightly cache, who owns the writer, and what is the fallback when it is
missing (halt loud vs. skip)?**

### D2 — UUP staging source

`load_sdca_extra_sources` (`strategies/sdca/optimize.py:186-…`) will read
`UUP.csv`/`UUP.parquet` sitting next to the price cache (`uup_path`, `:193`;
`uup_dates/uup_close` wired into `ExtraIndicatorSources`). But nothing stages
it: `export_sdca_macro.py`'s `SERIES_FILES` (`:44-52`) carries M2SL, GVZCLS,
WALCL, the BAML pair, T5YIE, NFCI only — no UUP — and the nightly job runs
fetch → export → generate (`pipeline-digiquant-tearsheets.yml:71-99`) with no
other macro-staging step. DTWEXBGS is explicitly skipped as off-panel
(`DTWEXBGS_SKIP_MESSAGE`). So: **at nightly runtime today, UUP.csv has no
producer.** The v3 weights (uup 0.5) assume a file the pipeline never writes.
Additionally, `generate_tearsheets.py` reads OHLCV plus extras from
`--cache-dir digiquant/data/price-history` — a flat CSV tree, not a manifest —
so there is no manifest to extend; the gap is a missing staging step, not a
missing manifest entry.

**OPEN: where do price/extra CSVs come from at nightly runtime — is UUP a new
`export_sdca_macro` series, a separate fetcher output, or a vendored static
file — and who verifies its freshness before a gold run?**

### D3 — weights passthrough design

Two shapes, stated without recommendation:

- **(a) Iterate the entry's `indicator_weights`.** Build the published weights
  from whatever keys the settings entry carries (validated against the catalog
  model), so `gold_sdca`'s 16-key map flows through untouched and future assets
  need no branch edit. Trade-offs: generic and future-proof; but an entry typo
  becomes a runtime shape, so unknown-key rejection and a provenance echo of
  the full map are load-bearing, not cosmetic.
- **(b) Extend the hardcoded list.** Add `uup` (+ gold macro keys) to the
  `:793-801` construction and the `:843-851` reporting tuple. Trade-offs:
  explicit, reviewable, matches the existing seven-key style; but it is the
  fourth such edit by count (BTC seven → gold N → next asset N+M) and re-locks
  the branch to a key roster.

Either way, the `dropped_this_run` report list (`:814-818`) must cover every
nonzero published weight (Site 2), and the `extras_unused` note must stop
claiming "power-law only" for composites.

**OPEN: generic passthrough (a) or extended explicit list (b) — and what
rejects an unknown weight key loudly?**

### D4 — `risk_model` dispatch design

Two shapes, stated without recommendation:

- **(a) Dispatch via `resolve_sdca_risk_model`.** The settings entry already
  declares `risk_model: generic_valuation`; route the branch through the
  existing resolver (`providers.py:48`), passing the branch's `idx_dates` +
  close. Trade-offs: honors the declared config, reuses the tested unknown-name
  `ValueError`; but `generic_valuation` fits QuantReg at runtime on the delayed
  frame — cost, determinism, and fit-failure behavior at nightly runtime are
  uncharacterized — and the `:834` BTC `load_coefficients()` call plus the
  `:888-891` coefficients provenance note need a per-model equivalent.
- **(b) Keep a hardcoded model per strategy.** Branch on strategy name (or keep
  BTC hardcoded and add a gold path). Trade-offs: no runtime fit, fully
  deterministic; but it duplicates Site 3 for every future asset and leaves the
  declared-but-ignored `risk_model` field as a trap.

Note the resolver's `rolling_z` third arm exists; the decision is about the
dispatch mechanism, not about re-litigating which model gold should use (the
settings entry already says `generic_valuation`).

**OPEN: resolver dispatch (a) or per-strategy hardcode (b) — and where do
non-BTC rails coefficients live, or is runtime fit the committed path?**

## 3. Acceptance criteria

A gold tearsheet is accepted when ALL hold:

1. `generate_tearsheets.py --strategy gold_sdca` (or the nightly equivalent
   invocation) completes from nightly-staged files — no hand-placed CSVs.
2. The uup 0.5 leg is live in the published index (provenance weights echo
   shows it nonzero; `dropped_this_run` is empty).
3. The drop-guard covers **all** nonzero published weights: any missing source
   series zeroes its weight AND names it in provenance (no silent leg loss).
4. Provenance names the preset (`gold_optimized`), the risk model actually
   used, the full weight map, and the GLD + UUP source windows.
5. The unit suite in §5 is green on the implementing branch, and the holdout
   number (−21.16%) is unchanged in `gold_optimized_provenance.json`
   (live-path work must not re-score or move the reserve).

## 4. Explicit non-goals

- No backfill redesign (GLD history before the seed span is out of scope).
- No new indicators, votes, rails, shapes, bars, or weight values.
- No bar/curve/geometry changes; the v3 winner is frozen.
- No coefficients file (runtime fit per recon — D4 decides the mechanism, not
  the principle).
- No `--push-supabase`, PR, merge, or nightly/fetcher/export edits in the
  scoping plan itself; no second holdout run for any reason (reserve spent in
  Task 1 — a rerun fails review).

## 5. Verification appendix (Task 3 evidence, 2026-10-01)

- Suite: `pytest tests/dq/strategies/sdca/test_presets.py
  tests/dq/strategies/sdca/test_asset_profile.py
  tests/dq/strategies/sdca/test_walk_forward.py
  tests/dq/strategies/sdca/test_optimize.py -m unit -q` → **57 passed**
  (2026-10-01, Task 3).
- Ruff: `ruff check digiquant/scripts/run_gold_holdout_validation.py` → all
  checks passed; `ruff format --check …` → 1 file already formatted.
- `git status --short` → plan commits `7b077674a`, `1a59bdafe`; this work
  order untracked at `digiquant/.scratch/gold_live_path_workorder.md`; no
  live-path file touched (`git diff --stat` empty).
