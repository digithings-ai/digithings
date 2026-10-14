# Gloomberb macro ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace digiquant macro-panel ingest for the 23 Gloomberb-backed FRED ids with anonymous `econ_series`, stop refreshing the 8 empty ids, and remove the `FRED_API_KEY` requirement from that path.

**Architecture:** Keep the sealed R2 dataset ids (`fred__{SERIES}`) and the `get_macro_series` read contract. Swap only the writer: `scripts/refresh_market_data_r2.py` and `digiquant prices fetch-macro` call `GloomberbClient.econ_series` (already in `digiquant/src/digiquant/data/gloomberb/`) and merge a short newest-page into the existing parquet. `#4796` (issue #4795) already skips every `fred` series when `FRED_API_KEY` is unset; the wire PR deletes that skip for the kept panel so cron fetches Gloomberb with no key. Yahoo FX, fedprob, and bitview stay on their current writers.

**Tech Stack:** Python 3.12, Polars, Pydantic v2 (`EconSeriesInput` / `EconSeriesObservation`), existing `GloomberbClient` (httpx via digifetch), R2 parquet generations in `digiquant.data.prices.r2_history`. No new dependency. No new host.

**Spec:** GitHub issue [#4794](https://github.com/digithings-ai/digithings/issues/4794). Sibling skip/fail-soft is [#4795](https://github.com/digithings-ai/digithings/issues/4795), landed as [#4796](https://github.com/digithings-ai/digithings/pull/4796) on `develop` at `01ef80df0`. This plan assumes that code. Do not re-implement #4795.

## Global Constraints

- Digi product names are lowercase in prose, docs, commits, and PR text (`digiquant`, `digigraph`, `gloomberb` the vendor). Code identifiers keep language casing (`GloomberbClient`, `MacroManifest`).
- Polars only on this path. Pydantic v2 models already exist; do not pass raw dicts across the new public functions except the existing `MacroObservation` TypedDict that `macro_ingest.py` already returns.
- Ruff line length 100. No inline imports unless a file already uses that pattern for optional HTTP clients.
- No secret values in code, tests, docs, or logs. Do not print `GLOOMBERB_SESSION_COOKIE`. `econ_series` is entitlement `free` and must not send a session cookie.
- `api.gloom.sh` is an existing dependency (`GLOOMBERB_BASE_URL` in `digiquant/src/digiquant/data/gloomberb/client.py`). Do not add a host, SDK, or package.
- Do not rewire prices, technicals, Yahoo FX, fedprob, or bitview onto Gloomberb. The enrichment-only rule in `digiquant/AGENTS.md` stays for those tools. The owner lock (2026-09-29, issue #4794) is the exception for this macro panel only.
- Do not touch `digikey/` or `digiquant/brokers/`.
- Tests that hit HTTP use `httpx.MockTransport` or an injected client. CI does not call `api.gloom.sh`.
- Branch for implementation: `task/<N>-slug` via `make task ISSUE=4794` (or a follow-up issue per PR). Base is `module/digiquant` when the diff is digiquant-only; a PR that also edits `.github/workflows/` or `apps/digiquant-runner/` follows `scripts/project_routing.json` for the labels it carries. This plan file is `component:root` and targets `develop`.
- `#4795` / `#4796` is in force: with `FRED_API_KEY` unset, `drop_fred_without_key` omits every `source=="fred"` spec and the job exits 0. Production runner has no key (`docs/ops/digiquant-runner.md`). Until the wire PR lands, `fred__*` stays stale on purpose.

---

## Locked decisions

1. **Dataset id stays `fred__{SERIES}`.** The prefix is the R2 dataset id, not a claim that the bytes came from `api.stlouisfed.org`. A rename to `gloomberb__*` would orphan every sealed generation and make `get_macro_series` miss, because `digiquant_get_macro_series` reads `macro_latest_pointer_key("fred", sid)` in `digiquant/src/digiquant/mcp_server.py` (`_read_r2_macro_window`). Successor keys are out of scope.
2. **Parquet `source` column stays `"fred"`.** `_normalize_macro_rows` projects onto `MACRO_COLUMNS = ("source", "series_id", "obs_date", "value", "unit")`. Widening the frame breaks `pl.concat` against backfill history. Row `meta` is stripped today and stays stripped.
3. **No alias for the 8 empty ids.** Live probe (2026-09-29) found no drop-in substitute. Do not map `DTWEXBGS` to Yahoo `DX-Y.NYB`, `MANEMP` to `PAYEMS`, or anything else. Consumers listed below lose a live refresh. Historical objects stay.
4. **Do not full-replace history with one `econ_series` page.** `EconSeriesInput.limit` is 1–1000 and the model has no `offset`, `observation_start`, or cursor (`digiquant/src/digiquant/data/gloomberb/models.py`). A 1000-row desc page is about four years of business days. The current restatement branch calls `fetch_macro_full` from `1990-01-01` and replaces the frame. Pointing that branch at Gloomberb would delete the pre-page history. Incremental cron merges a short newest page. Restatement overwrites only dates present in that page.
5. **One Gloomberb client per refresh, sequential, `cache_ttl=0`.** The enrichment cache is 900s and is wrong for a seal. The 0.5s `RateLimiter` stays. Do not spawn 23 parallel clients.
6. **A set `FRED_API_KEY` does not keep the FRED writer.** After the wire PR, the panel does not call `api.stlouisfed.org`. Leaving the key in an environment must not dual-write.
7. **`digifetch_econ_series` is unchanged.** It remains the live anonymous MCP/read tool (limit ≤ 1000). It is not the pipeline writer and it is not blocked from the 8 ids. Research grounding stays `get_macro_series` (sealed R2) plus the existing `MACRO_TOOLS` cohort.

---

## Series panel

Source manifest: `digiquant/src/digiquant/research/config/macro_series.yaml` (`fred.series`, 31 ids). `backfill_start: "1990-01-01"` stays as documentation of the sealed history; Gloomberb does not honor it as a query parameter.

### Kept (23) — refresh from Gloomberb

| id | cadence in YAML | unit |
|----|-----------------|------|
| `DGS2` `DGS5` `DGS10` `DGS30` | daily (key omitted) | percent |
| `DFF` `SOFR` | daily | percent |
| `T10Y2Y` `T10Y3M` | daily | percent |
| `T10YIE` `T5YIE` `DFII10` `T5YIFR` | daily | percent |
| `BAMLH0A0HYM2` `BAMLC0A0CM` | daily | percent |
| `VIXCLS` `VXVCLS` | daily | index |
| `DCOILWTICO` | daily | usd_per_barrel |
| `M2SL` `UNRATE` `CPIAUCSL` `PCEPI` | monthly | billions_usd / percent / index / index |
| `WALCL` `ICSA` | weekly | millions_usd / persons |

### Dropped (8) — remove from the manifest, do not fetch

| id | why it matters downstream |
|----|---------------------------|
| `VXNCLS` `GVZCLS` `OVXCLS` | `alt-options-derivatives` skill and `tests/dq/research/test_phase_tool_flags.py::test_macro_series_yaml_has_volatility_complex`. `VIXCLS` + `VXVCLS` stay, so the VIX / VIX3M term structure stays. Nasdaq, gold, and crude vol leave the panel. |
| `DTWEXBGS` | `MacroLiquidityModel` default `dxy` vote; SDCA sibling `DTWEXBGS.csv` via `digiquant/scripts/export_sdca_macro.py` and `pipeline-digiquant-tearsheets.yml`; forex and macro skills; `apps/dashboard/lib/macro-curated.ts`; `get_macro_series` tool blurb in `digiquant/src/digiquant/research/data/tools.py`. |
| `MANEMP` | Default `pmi` vote (YoY) in `DEFAULT_MACRO_SPECS`. |
| `NFCI` `STLFSI4` `MORTGAGE30US` | Weekly panel series. Cadence tests in `tests/scripts/test_refresh_market_data_r2_macro.py` list them. No skill requires them by name. |

Frozen sets live in one module so YAML, tests, and the probe cannot drift:

```python
KEPT_SERIES_IDS: frozenset[str] = frozenset({
    "DGS2", "DGS5", "DGS10", "DGS30", "DFF", "SOFR",
    "T10Y2Y", "T10Y3M", "T10YIE", "T5YIE", "DFII10", "T5YIFR",
    "BAMLH0A0HYM2", "BAMLC0A0CM", "VIXCLS", "VXVCLS", "DCOILWTICO",
    "M2SL", "UNRATE", "CPIAUCSL", "PCEPI", "WALCL", "ICSA",
})
DROPPED_SERIES_IDS: frozenset[str] = frozenset({
    "VXNCLS", "GVZCLS", "OVXCLS", "DTWEXBGS",
    "MANEMP", "NFCI", "STLFSI4", "MORTGAGE30US",
})
```

`len(KEPT_SERIES_IDS) == 23`, `len(DROPPED_SERIES_IDS) == 8`, intersection empty.

---

## R2 key layout

Unchanged. Helpers in `digiquant/src/digiquant/data/prices/r2_history.py`:

| object | key |
|--------|-----|
| generation | `market-data/macro/fred__{SERIES}/{as_of}.parquet` |
| same-day restatement | `market-data/macro/fred__{SERIES}/{as_of}--{sha12}.parquet` |
| latest pointer | `market-data/macro/fred__{SERIES}/latest` |
| manifest dataset id | `fred__{SERIES}` inside `market-data/manifest.json` |
| registry `source_table` | `market-data/macro` |

`{SERIES}` is the FRED id as written (`DGS10`, not lowercased). `{as_of}` is the max `obs_date` in the sealed frame (`YYYY-MM-DD`). Pointer value is the generation key. Writes stay `put → SHA-256 read-back → registry insert → swap pointer`. Never overwrite a generation in place.

Columns inside the parquet stay `source`, `series_id`, `obs_date`, `value`, `unit` with `source="fred"`.

Dropped ids: do not delete objects and do not flip pointers. `latest` keeps serving the last seal. Refresh stops selecting them once they leave the YAML, so the pointer ages. That stale serve is allowed. An operator delete is a later, explicit bucket change, not this epic.

Yahoo FX keys (`yahoo__FX/EUR` and the rest of `YAHOO_FX_DEFAULT`) are not part of this layout change.

Core mirror: `CORE_MIRROR_MACRO_SOURCES` stays `{"yahoo"}`. Do not start mirroring `fred` rows back into `macro_series_observations`. twelve-x reads Yahoo FX from that table; FRED readers already moved to R2 (#3780). `prices-eod-macro` with `run_writers=true` is not on the Phase 1 cron (`docs/ops/digiquant-runner.md`: cron never sends `run_writers`).

---

## `get_macro_series` impact

Two readers, one contract. Neither gains a parameter.

### MCP — `digiquant_get_macro_series`

`digiquant/src/digiquant/mcp_server.py`

- Args stay `series_ids: list[str]`, `lookback: int = 6` (capped at 500), `as_of: str | None`.
- R2 envelope stays `{"as_of", "series", "stale"}` with per-id `{latest, window}`.
- Lookup is still `macro_latest_pointer_key("fred", sid)`. Kept ids keep resolving after the writer swap because the pointer path did not change.
- Unknown id, or an id whose pointer is missing, still raises `LookupError` and the tool returns `{"error": "..."}`. A dropped id with a leftover pointer still returns the last seal. Document that in the tool description. Do not special-case the 8 into a hard error: agents that already stored a pointer keep a stale window instead of a broken call.
- `stale` is still the manifest seal age. Macro still has no live overlap on the read path. The writer change does not add a Gloomberb fetch inside the MCP request.
- Supabase fallback (`r2_backend_enabled()` false) still selects `macro_series_observations` by `series_id` only. That table is not the production read. Do not add a Gloomberb fallback inside the tool.

### Research — `digiquant.research.data.queries.get_macro_series`

- Signature stays `(*, client, series_ids, lookback=6, as_of=None) -> {series_id: {latest, window}}`.
- R2 branch `_r2_macro_series` calls `_read_r2_macro_window`. Same pointer. A missing series is an empty `{latest: {}, window: []}` here (research fail-soft), which is the existing split versus MCP's loud error. Do not unify it in this epic.
- `get_market_context` still asks for `lookback=2`. Series that leave the injected context list must be edited in the skill/tool text, not by changing the query function.
- `DATA_TOOLS` description in `digiquant/src/digiquant/research/data/tools.py` currently names `DTWEXBGS`. Replace that example with a kept id (`DGS2` is already in the sentence; drop `DTWEXBGS` only).

### What does not change

- `digifetch_econ_series` registration, entitlement `free`, path `GET /cloud/econ/series/{seriesId}`, params `limit` and `sortOrder`.
- `MACRO_TOOLS` membership (`digifetch_econ_series` stays). Phase 3 macro still grounds on `get_macro_series` first.
- In-process tool name stays `get_macro_series`. No new MCP tool.

### Skill and preview edits (PR 3)

| surface | edit |
|---------|------|
| `research/skills/alt-options-derivatives/SKILL.md` | Request `VIXCLS` and `VXVCLS` only. Say `VXNCLS`, `GVZCLS`, `OVXCLS` are not on the panel. |
| `research/skills/forex/SKILL.md` | Stop telling the agent to call `get_macro_series` for `DTWEXBGS`. Dollar view stays on the Yahoo FX pairs plus `DGS10` / `DGS2`. |
| `research/skills/macro/SKILL.md` | Remove `DTWEXBGS` from the call list. |
| `apps/dashboard/lib/macro-curated.ts` | Remove `DTWEXBGS` from `MACRO_PREVIEW_SERIES_IDS`. Leave `DEXUSEU` (it was never in this YAML). |
| `tests/dq/research/test_phase_tool_flags.py` | `test_macro_series_yaml_has_volatility_complex` asserts `{"VIXCLS", "VXVCLS"} <= ids` and `DROPPED_SERIES_IDS` disjoint from ids. |
| `indicators/macro_liquidity.py` | `DEFAULT_MACRO_SPECS` becomes `M2SL` (yoy, +) and `UNRATE` (level, −). Delete the `dxy` and `pmi` specs. Docstring states the 2026-09-29 panel drop. Callers can still pass a `DTWEXBGS` spec if they hold their own frame; the model does not fetch. |
| `scripts/export_sdca_macro.py` | Stop calling `fetch_fred_series` and stop calling `fredgraph.csv` for `DTWEXBGS`. Staging `M2SL.csv` still reads the sealed R2 `fred__M2SL` generation (or the existing Supabase rows if present). If `DTWEXBGS.csv` cannot be built without FRED, log a single warning and omit the file so `dxy_weight` zeros loudly in the existing SDCA loader, and say so in the tearsheet notes. Do not add Yahoo `DX-Y.NYB` here. |
| `tests/scripts/test_refresh_market_data_r2_macro.py` | Cadence fixture lists drop `MANEMP`, `NFCI`, `STLFSI4`, `MORTGAGE30US`. Monthly assertion keeps `M2SL`, `UNRATE`, `CPIAUCSL`, `PCEPI`. Weekly assertion keeps `WALCL`, `ICSA`. |

`tests/dq/research/test_context_diet.py` `_MACRO_SERIES` includes `DTWEXBGS`, `FEDFUNDS`, and `PAYEMS` as synthetic context. That fixture is not the manifest. Leave it unless a test asserts those ids are fetched. Do not treat `PAYEMS` as a `MANEMP` replacement.

---

## History, rate limit, and terms

### History

`econ_series` returns a single page. Client contract (`EconSeriesInput`): `limit` default 100, max 1000, `sort_order` `asc|desc` (wire name `sortOrder`). Missing prints (`"."`) already become `null` in `normalize_econ_series` and must be dropped before a row is sealed, matching `fred_observations_to_rows`.

There is no proven way to ask for `observation_start=1990-01-01`. Do not add `offset` or `startDate` to `EconSeriesInput` in this epic. The probe script (below) records the oldest date at `limit=1000`. If a later live run shows a paging field that already works, file a follow-up issue. Do not block the cron on it.

Writer rules:

| situation | request | seal |
|-----------|---------|------|
| Incremental cron, history exists | `sort_order=desc`, `limit=window_limit(cadence)`, then keep rows with `obs_date` in `[run - cadence_window, run]` | Append `obs_date > seal`. If a value inside the overlap changed, overwrite those dates in the existing frame and keep older rows. Do not call `fetch_macro_full`. |
| Empty history (new bucket) | `limit=1000`, `sort_order=desc` | Seal that page only. Outcome note contains `truncated`. Do not invent rows before the oldest returned date. |
| Restatement of a print older than the page | not fetched | Last sealed value stands. This is the gap versus FRED `realtime_start`. |

`window_limit` (observation count, not days):

| cadence | existing fetch window (`_CADENCE_WINDOW_DAYS`) | `window_limit` |
|---------|--------------------------------------------------|----------------|
| omitted or `daily` | 45 | 60 |
| `weekly` | 45 | 16 |
| `monthly` | 120 | 8 |
| `quarterly` | 240 | 4 |

60 daily slots cover a 45-day window plus weekends and a revision. 16 weekly slots cover more than 45 days. 8 monthly slots cover the 120-day window. All are ≤ 1000.

`FRED_OVERLAP_DAYS = 14` in `macro_ingest.py` is unused by the R2 refresh (the refresh uses the cadence window). Leave the constant. Do not copy it into the Gloomberb limit.

### Rate limit

Client constants, do not change them in this epic (`client.py`):

| knob | value |
|------|-------|
| `DEFAULT_MIN_INTERVAL_SECONDS` | 0.5 |
| `DEFAULT_CACHE_TTL_SECONDS` | 900 (ingest client passes `cache_ttl=0` instead) |
| `DEFAULT_CIRCUIT_FAILURE_THRESHOLD` | 3 |
| `DEFAULT_CIRCUIT_RESET_SECONDS` | 60 |
| `DEFAULT_MAX_RETRY_AFTER_SECONDS` | 5 |
| `GLOOMBERB_ENABLED` | default on; any value other than `1`/`true`/`yes`/`on` disables the family |

Volume for the panel: 23 sequential GETs per refresh. Pacing floor is `23 * 0.5s ≈ 12s`, inside `market-data-refresh` `timeout_seconds: 1800`. A second cron the same day is another 23 calls. `prices-eod-macro` does not add a call on the Phase 1 clock because cron does not pass `run_writers`.

A 429 becomes the existing typed `rate_limited` error. The refresh treats that series as `history-only` (today's `FetchError` path). A daily series in `history-only` still fails the staleness gate (exit 1). A monthly series in `history-only` stays exempt via `SLOW_CADENCES`. Do not mark a Gloomberb outage as success. That is the opposite of `#4796`, which skips only because the FRED key is absent.

`GLOOMBERB_ENABLED` off: every kept series is `history-only` with note `gloomberb disabled`. Daily series then fail the gate. The runner does not set the variable, so the client default (on) applies. Do not add the variable to `commands.json` unless an operator needs the kill switch; default-on must keep working with the variable unset.

### Terms and positioning

`docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md` §6 and §10:

- Cloud market data is enrichment-only because of delay and rate limits. This epic does **not** apply that verdict to quotes or price history.
- The macro panel exception is the owner lock on #4794: anonymous `econ_series` becomes the writer for the 23 ids. Delay on econ prints is the publisher lag (a monthly CPI print), not the 15-minute equity delay. Say that in `digiquant/AGENTS.md`. Do not stamp "delayed up to 15 minutes" on these parquet rows.
- Code license of the Gloomberb terminal app is MIT. Data terms for `api.gloom.sh` at production volume have **not** been reviewed (spec §10). This plan does not claim a review. Recorded volume is the 23 GETs per refresh above, anonymous, no cookie, same host the MCP container already uses.
- Attribution string `"Sourced from Gloomberb"` stays on digifetch tool envelopes. It is not written into the parquet (the column contract has nowhere to put it). Research copy that quotes a sealed macro value does not need a new attribution line in this epic; the digifetch tool path already attributes live calls.
- `agents.yml` `human_gates` "new external service" does not trip: no new host. Implementation PRs still do not self-merge if they touch live-trading or `digikey/`. This path touches neither.

### Probe script

Create `scripts/probe_gloomberb_macro_panel.py`. It accepts an injected client. For each id in `KEPT_SERIES_IDS | DROPPED_SERIES_IDS` it calls `econ_series` with `limit=1000`, `sort_order=desc` and prints `id`, `status` (`ok` / `empty` / `error`), `n`, `oldest`, `newest`. No headers, cookies, or keys.

- Exit 0 when every kept id is `ok` and every dropped id is `empty`.
- Exit 2 on drift (kept id empty or error, or dropped id `ok`).
- Unit test uses a fake client. No network marker in CI.

The 2026-09-29 probe is the baseline the frozen sets encode. Re-run the script by hand before the wire PR merges if more than a few days have passed. Do not check in the probe's stdout.

---

## Modules

| module | responsibility |
|--------|----------------|
| `digiquant/src/digiquant/data/prices/gloomberb_macro.py` (new) | Frozen id sets, `window_limit`, `gloomberb_observations_to_rows`, `fetch_gloomberb_series`, `fetch_gloomberb`, `build_ingest_client`. No R2, no YAML I/O, no Supabase. |
| `digiquant/src/digiquant/data/prices/macro_ingest.py` | Unchanged fetchers for Yahoo FX. `fetch_fred` / `fetch_fred_series` stay until PR 3 removes the last caller, then delete them in that PR if `rg fetch_fred` is clean. |
| `digiquant/src/digiquant/data/gloomberb/client.py` | No endpoint or model changes. Ingest calls `econ_series` only. |
| `scripts/refresh_market_data_r2.py` | `_fetch_macro` `source=="fred"` calls the new module. Delete `drop_fred_without_key` usage so a missing key does not skip the panel. Restatement for `fred` merges the page. |
| `digiquant/src/digiquant/cli/prices.py` | `fetch-macro` source `fred` calls `fetch_gloomberb`. Missing `FRED_API_KEY` is not a skip and not an error. |
| `digiquant/src/digiquant/mcp_server.py` | Read path unchanged. Description text only if it names FRED as the live vendor. |
| `apps/digiquant-runner/commands.json` | Remove `FRED_API_KEY` from `market-data-refresh` and `prices-eod-macro` `env` arrays after the writer no longer reads it. |
| `docs/ops/digiquant-runner.md`, `digiquant/ARCHITECTURE.md`, `digiquant/AGENTS.md` | Replace the "stale until #4794" sentences with the writer exception, the key layout, and the history gap. |

### Interface PR 2 consumes

```python
def window_limit(cadence: str | None) -> int:
    key = (cadence or "daily").strip().lower()
    try:
        return {"daily": 60, "weekly": 16, "monthly": 8, "quarterly": 4}[key]
    except KeyError:
        raise ValueError(
            f"unknown cadence {cadence!r}; expected daily, weekly, monthly, quarterly"
        ) from None

def gloomberb_observations_to_rows(
    series_id: str,
    unit: str | None,
    title: str | None,
    observations: list[Any],
) -> list[MacroObservation]:
    """Drop null values and blank dates. source='fred'. meta title only, stripped later by refresh."""

def build_ingest_client() -> GloomberbClient:
    """cache_ttl=0. Default RateLimiter, breaker, and enabled-flag. No session cookie attached by econ_series."""

class GloomberbMacroError(RuntimeError):
    """One series failed (disabled, rate_limited, upstream_error, empty page)."""

def fetch_gloomberb_series(
    client: Any,
    series_id: str,
    *,
    unit: str | None,
    title: str | None,
    limit: int,
) -> list[MacroObservation]:
    """One econ_series call, sort_order desc. Raises GloomberbMacroError. Does not raise on a sibling series."""

def fetch_gloomberb(
    manifest: MacroManifest,
    client: Any,
    *,
    only_series: str | None = None,
    limit_for: Callable[[str | None], int] = window_limit,
) -> list[MacroObservation]:
    """Walk manifest.fred_series. Isolate per-series errors. Raise RuntimeError only when every attempted series failed."""
```

`limit_for` receives the YAML `cadence` string (or `None`). `fetch_gloomberb_series(..., limit=1000)` is the empty-history tail. Both entry points are pure enough to test with a fake client that records `limit` and returns an `EconSeriesEnvelope`.

---

## File touch list

### PR 1 — adapter and probe (no cron behavior change)

- Create: `digiquant/src/digiquant/data/prices/gloomberb_macro.py`
- Create: `tests/dq/data/test_gloomberb_macro.py`
- Create: `scripts/probe_gloomberb_macro_panel.py`
- Create: `tests/scripts/test_probe_gloomberb_macro_panel.py`
- Modify: `digiquant/ARCHITECTURE.md` — one paragraph under the macro ingest section pointing at the new module and stating it is not wired yet. The wire PR replaces that sentence.

### PR 2 — wire writers (depends on PR 1 merged)

- Modify: `scripts/refresh_market_data_r2.py` (`_fetch_macro`, `refresh_macro_series` restatement branch for `source=="fred"`, delete the `drop_fred_without_key` call in `main`, drop `fred_skipped` from the artifact or write `[]`)
- Modify: `tests/scripts/test_refresh_market_data_r2_macro.py` and any test that asserts `fred_skipped` / missing-key skip (search `drop_fred_without_key` and `FRED_API_KEY unset`)
- Modify: `digiquant/src/digiquant/cli/prices.py` `fetch_macro_cmd`
- Modify: tests that assert `FRED_API_KEY required` or the #4796 skip echo for `fetch-macro` (search `fred__* stays stale`)
- Modify: `apps/digiquant-runner/commands.json` env arrays
- Modify: `apps/digiquant-runner/wrangler.toml` comment, `docs/ops/digiquant-runner.md`
- Modify: `.github/workflows/pipeline-market-data-refresh.yml`, `pipeline-digiquant-prices.yml`, `pipeline-digiquant-tearsheets.yml` — stop passing `FRED_API_KEY` into the macro steps this epic owns. Leave the secret in GitHub; do not rotate or print it.
- Modify: `digiquant/AGENTS.md` enrichment-only bullet with the panel exception
- Modify: `digiquant/ARCHITECTURE.md` so the "not wired yet" sentence is gone

### PR 3 — panel contract (parallel with PR 2 after PR 1, or in parallel with PR 1 if it does not import the adapter except the frozen sets)

PR 3 may duplicate the two frozensets only if PR 1 has not merged; prefer importing them from `gloomberb_macro.py` so there is one list. If PR 3 merges first, it defines the sets and PR 1 imports them. Do not define them twice. Agree the sets as written in this plan.

- Modify: `digiquant/src/digiquant/research/config/macro_series.yaml`
- Modify: the skill files, `tools.py` description, `macro_liquidity.py`, `export_sdca_macro.py`, `apps/dashboard/lib/macro-curated.ts`
- Modify: `tests/dq/research/test_phase_tool_flags.py`, `tests/dq/indicators/test_macro_liquidity.py`, `tests/dq/test_export_sdca_macro.py`, `tests/scripts/test_refresh_market_data_r2_macro.py` cadence lists
- Modify: `digiquant/src/digiquant/research/docs/ops/data-sources.md`, `digiquant/src/digiquant/research/config/data-sources.md`, `digiquant/src/digiquant/research/docs/RUNBOOK.md` FRED-key paragraphs
- Modify: `digiquant/pyproject.toml` comment that says M2 requires `FRED_API_KEY`
- Delete `fetch_fred` / `fetch_fred_series` only at the end of PR 3 when `rg "fetch_fred" --glob '!docs/**'` shows no remaining callers. Until then keep them so an unmerged PR 2 still compiles. If PR 2 has already stopped calling them, delete in PR 3.
- `scripts/validation/build_m2_composite.py` and `docs/research/equity_valuation_sdca_check.py` are research one-offs that call FRED or keyless `fredgraph.csv` directly. Point their module docstrings at this plan and leave the scripts. Do not silently switch them to Gloomberb inside PR 3.

---

## Phased PRs

```
PR 1 adapter + probe          (library, tests, no writer change)
        |                 \
        v                  v
PR 2 wire refresh + CLI    PR 3 YAML, skills, liquidity, SDCA, dashboard
```

PR 2 and PR 3 touch different files except `test_refresh_market_data_r2_macro.py` cadence lists (PR 3) versus fetch tests (PR 2). Split that file's edits by test function so the two PRs do not conflict: PR 2 adds fetch tests at the bottom; PR 3 edits the existing cadence-id tuples.

Do not start PR 2 from a branch that still skips `fred` when the key is missing. The production runner has no key, so a half-wire that fetches Gloomberb only when the key is set will never run.

### PR 1 tasks

- [ ] **Step 1: Write failing tests** in `tests/dq/data/test_gloomberb_macro.py`.

```python
import pytest
from digiquant.data.prices.gloomberb_macro import (
    DROPPED_SERIES_IDS,
    KEPT_SERIES_IDS,
    gloomberb_observations_to_rows,
    window_limit,
)

pytestmark = pytest.mark.unit

def test_panel_sets_are_the_probed_split() -> None:
    assert len(KEPT_SERIES_IDS) == 23
    assert len(DROPPED_SERIES_IDS) == 8
    assert KEPT_SERIES_IDS.isdisjoint(DROPPED_SERIES_IDS)
    assert "DGS10" in KEPT_SERIES_IDS and "M2SL" in KEPT_SERIES_IDS
    assert "DTWEXBGS" in DROPPED_SERIES_IDS and "MANEMP" in DROPPED_SERIES_IDS

def test_window_limit_covers_cadence_and_rejects_unknown() -> None:
    assert window_limit(None) == 60
    assert window_limit("daily") == 60
    assert window_limit("weekly") == 16
    assert window_limit("monthly") == 8
    assert window_limit("quarterly") == 4
    with pytest.raises(ValueError, match="unknown cadence"):
        window_limit("hourly")

def test_rows_drop_null_prints_and_stamp_fred_source() -> None:
    rows = gloomberb_observations_to_rows(
        "DGS10",
        "percent",
        "10Y",
        [
            {"date": "2026-01-02", "value": 4.2},
            {"date": "2026-01-03", "value": None},
            {"date": "", "value": 4.3},
        ],
    )
    assert rows == [
        {
            "source": "fred",
            "series_id": "DGS10",
            "obs_date": "2026-01-02",
            "value": 4.2,
            "unit": "percent",
            "meta": {"title": "10Y"},
        }
    ]
```

Add `test_fetch_gloomberb_series_requests_desc_limit` with a fake client that records kwargs and returns an envelope whose `data.observations` are two dated values. Assert the call is `series_id="CPIAUCSL"`, `limit=8`, `sort_order="desc"`, and both rows come back with `source=="fred"`.

Add `test_fetch_gloomberb_isolates_one_failure` on a two-series manifest: first id raises `GloomberbMacroError`, second returns one row. Assert one row and that a manifest where both fail raises `RuntimeError` matching `all`.

Add `test_fetch_gloomberb_empty_page_is_an_error`: observations `[]` raises `GloomberbMacroError` matching `empty`.

Add `test_build_ingest_client_disables_cache`: `build_ingest_client()` returns a `GloomberbClient` whose `_cache_ttl` is `0` (`GloomberbClient.__init__` stores the argument on `self._cache_ttl`). Assert no session cookie is required by calling `fetch_gloomberb_series` against a fake that does not read env.

Probe tests in `tests/scripts/test_probe_gloomberb_macro_panel.py`:

```python
def test_probe_exits_0_when_split_matches() -> None:
    # fake client: kept ids return one observation, dropped ids return []
    assert classify(fake).exit_code == 0

def test_probe_exits_2_when_a_kept_id_is_empty() -> None:
    assert classify(fake_with_dgs10_empty).exit_code == 2
```

`classify` is a pure function in the probe script so the test does not spawn a process. `main` calls it.

- [ ] **Step 2: Run the new tests and confirm they fail** on import.

```bash
PATH="$PWD/.venv/bin:$PATH" pytest -m unit \
  tests/dq/data/test_gloomberb_macro.py \
  tests/scripts/test_probe_gloomberb_macro_panel.py -q
```

Expected: collection error, `gloomberb_macro` missing.

- [ ] **Step 3: Implement** `gloomberb_macro.py` and the probe script to the interface above. Map observations with attribute or mapping access (`date` / `value`) so both the normalizer model and a dict fixture work. Use `EconSeriesInput` through the real client in `fetch_gloomberb_series` when `client` is a `GloomberbClient`; the fake only needs `.econ_series`. If the envelope's `data` is a `DigifetchError` or `data is None`, raise `GloomberbMacroError` with `error.code` in the message (`rate_limited`, `upstream_error`, `invalid_input`). Disabled family uses the same error with code `disabled`.

- [ ] **Step 4: Re-run the tests.** Expected: pass. Then `ruff check` and `ruff format --check` on the new files.

- [ ] **Step 5: Commit** `feat(digiquant): add gloomberb macro page adapter`.

PR 1 does not change `drop_fred_without_key`. Cron stays on the #4796 skip until PR 2.

### PR 2 tasks

- [ ] **Step 1: Failing refresh test.** Put the new cases in `tests/scripts/test_refresh_market_data_r2_gloomberb.py` so PR 3 can edit cadence id tuples in `test_refresh_market_data_r2_macro.py` without overlapping this file. Load the refresh module the same way that file does (`importlib` on `scripts/refresh_market_data_r2.py`).

`refresh_macro_series` calls `store.fetch_macro(source, series, start, end)`. Thread cadence as a keyword-only argument with default `None`, and pass it from `refresh_macro_series`. Update the existing `FakeStore.fetch_macro` in `test_refresh_market_data_r2_macro.py` to `def fetch_macro(self, source, series, start, end, *, cadence=None)` so those window tests keep collecting. That signature edit belongs to PR 2 only.

```python
def test_fred_fetch_uses_gloomberb_and_ignores_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    calls: dict[str, object] = {}

    def fake_fetch(manifest, client, *, only_series, limit_for):
        calls["series"] = only_series
        cadence = manifest.fred_series[0].get("cadence")
        calls["limit"] = limit_for(cadence)
        return [{
            "source": "fred",
            "series_id": "DGS10",
            "obs_date": "2026-09-23",
            "value": 4.1,
            "unit": "percent",
        }]

    monkeypatch.setattr(
        "digiquant.data.prices.gloomberb_macro.fetch_gloomberb",
        fake_fetch,
    )
    store = refresh.RefreshStore.__new__(refresh.RefreshStore)
    rows = store._fetch_macro("fred", "DGS10", "2026-08-01", "2026-09-24", cadence=None)
    assert calls["series"] == "DGS10"
    assert calls["limit"] == 60
    assert rows[0]["value"] == 4.1
```

`RefreshStore.__new__` skips the R2 backend constructor. `_fetch_macro` for `source=="fred"` must not touch `self` beyond the call into `fetch_gloomberb`. Do not construct a live R2 client.

Second test, on the same `FakeStore` shape as `test_refresh_market_data_r2_macro.py` (history in, `put` captures the frame). History contains `obs_date=2020-01-02`, `value=1.0`, plus a sealed overlap date whose live value differs. `fetch_macro` returns only the overlap row. After `refresh_macro_series("fred", "DGS10", store, {}, as_of=RUN)`, the sealed frame still contains the `2020-01-02` row and the revised overlap value. Monkeypatch `store.fetch_macro_full` to raise `AssertionError`. Yahoo's full re-pull stays; this assertion is only for `source=="fred"`.

Third test: `main` no longer calls `drop_fred_without_key`. With the key unset, a one-series fred manifest reaches `_fetch_macro` (assert via the fake above, not via `--dry-run`). The artifact either omits `fred_skipped` or sets it to `[]`.

Fourth test: `fetch-macro` with source `fred`, `FRED_API_KEY` unset, not dry-run, `fetch_gloomberb` patched to return one row, exits 0 and does not echo `stale until #4794`.

- [ ] **Step 2: Run those tests.** Expected: fail, because `_fetch_macro` still reads `FRED_API_KEY` and `main` still calls `drop_fred_without_key`.

- [ ] **Step 3: Implement the wire.**

Give `_fetch_macro` and `fetch_macro` a keyword-only `cadence: str | None = None`. `refresh_macro_series` passes the cadence it already has. Keep the import inside the branch, matching the Yahoo import already in this function (the refresh file is loaded as a script).

```python
if source == "fred":
    from digiquant.data.prices.gloomberb_macro import (
        GloomberbMacroError,
        build_ingest_client,
        fetch_gloomberb,
        window_limit,
    )
    from digiquant.data.prices.macro_ingest import MacroManifest

    manifest = MacroManifest(
        fred_series=[{"id": series, "cadence": cadence}],
        fred_backfill_start=start,
    )
    try:
        rows = fetch_gloomberb(
            manifest,
            build_ingest_client(),
            only_series=series,
            limit_for=lambda _cadence: window_limit(cadence),
        )
    except (GloomberbMacroError, RuntimeError) as exc:
        raise FetchError(f"{source}__{series}", str(exc)) from exc
    return [r for r in rows if start <= str(r["obs_date"]) <= end]
```

`limit_for` ignores the per-item cadence argument and uses the cadence `refresh_macro_series` passed, so a one-series manifest cannot disagree with the window. `window_limit` still raises on an unknown cadence.

Empty history (`hist is None`) for `source=="fred"` must not call `fetch_macro_full`. Call `fetch_gloomberb_series(..., limit=1000)` and seal that page. Outcome note contains `truncated`. Yahoo's empty-history path still calls `fetch_macro_full`.

In `refresh_macro_series`, when `source == "fred"` and `_restated(...)` is true:

```python
merged = pl.concat([hist, live]).unique(subset=["obs_date"], keep="last").sort("obs_date")
```

Seal `merged` with the existing `_put_macro` / same-day restatement key path. Note: `window restatement; rows before the gloomberb page kept`. Do not call `_fetch_full`. Yahoo keeps the full re-pull.

Delete the `drop_fred_without_key(macro_specs)` call. Remove the skip log. A missing key is normal.

`fetch_macro_cmd`: if `"fred" in sources_set`, call `fetch_gloomberb(mani, build_ingest_client())` with `limit_for` using each series' cadence (`window_limit`). Do not read `FRED_API_KEY`. `--dry-run` prints the series ids and does not construct a client. `--backfill` uses `limit=1000` per series and the command docstring says the page is a tail, not 1990.

Runner: remove `"FRED_API_KEY"` from the two `env` arrays in `apps/digiquant-runner/commands.json`. Update the wrangler comment and `docs/ops/digiquant-runner.md` so they no longer say the generations stay stale until #4794. They say the panel is Gloomberb, the 8 ids are not refreshed, and history before the page is whatever was already sealed.

Workflows: delete the `FRED_API_KEY: ${{ secrets.FRED_API_KEY }}` line on the market-data refresh job and on the digiquant prices / tearsheet jobs that only needed it for this panel. If a job still runs a script that calls `fetch_fred` until PR 3, leave the env on that job and note it in the PR body. Do not print the secret.

- [ ] **Step 4: Tests pass.** Commands:

```bash
PATH="$PWD/.venv/bin:$PATH" pytest -m unit \
  tests/dq/data/test_gloomberb_macro.py \
  tests/scripts/test_refresh_market_data_r2_macro.py \
  tests/scripts/test_refresh_market_data_r2_gloomberb.py \
  tests/scripts/test_market_data_refresh_workflow.py \
  tests/dq/data/test_macro_ingest.py -q --tb=short
```

Expected: pass. `test_macro_ingest.py` still covers `fetch_fred` until PR 3 deletes it.

```bash
PATH="$PWD/.venv/bin:$PATH" ruff check scripts/refresh_market_data_r2.py \
  digiquant/src/digiquant/cli/prices.py digiquant/src/digiquant/data/prices/gloomberb_macro.py
PATH="$PWD/.venv/bin:$PATH" ruff format --check \
  scripts/refresh_market_data_r2.py digiquant/src/digiquant/cli/prices.py
```

- [ ] **Step 5: Commit** `feat(digiquant): seal macro panel from gloomberb econ series`.

### PR 3 tasks

- [ ] **Step 1: Failing contract tests.**

```python
def test_manifest_matches_probed_panel() -> None:
    from digiquant.data.prices.gloomberb_macro import DROPPED_SERIES_IDS, KEPT_SERIES_IDS
    from digiquant.data.prices.macro_ingest import MacroManifest
    manifest = MacroManifest.from_yaml(
        "digiquant/src/digiquant/research/config/macro_series.yaml"
    )
    ids = {s["id"] for s in manifest.fred_series}
    assert ids == KEPT_SERIES_IDS
    assert ids.isdisjoint(DROPPED_SERIES_IDS)

def test_default_liquidity_specs_match_live_panel() -> None:
    from digiquant.indicators.macro_liquidity import DEFAULT_MACRO_SPECS
    assert {s.series_id for s in DEFAULT_MACRO_SPECS} == {"M2SL", "UNRATE"}
```

Update `test_macro_series_yaml_has_volatility_complex` in the same commit as the YAML edit so the suite is never red on `develop` mid-file. Update the macro-liquidity tests that build a frame for `DTWEXBGS` / `MANEMP`: keep them as explicit custom-spec tests (the model still accepts those ids when the caller passes frames) and add one test that the default specs no longer include them.

`export_sdca_macro`: test that with no `FRED_API_KEY` and no network, `M2SL` rows can be built from an injected R2 frame, and `DTWEXBGS` produces the warning plus zero rows rather than a `fetch_fred_series` call.

Dashboard: if `macro-curated.ts` has a test, assert `DTWEXBGS` is absent. If it has no test, the YAML/python tests are the gate; do not add a new frontend harness for one string.

- [ ] **Step 2: Run the contract tests.** Expected: fail on the current 31-id YAML and the four default specs.

- [ ] **Step 3: Edit the files in the touch list.** YAML header comment says the `fred:` block is the Gloomberb panel (dataset id remains `fred`) and names the 8 dropped ids so a later reader does not re-add them without a probe. Skills use the wording in the impact table. `export_sdca_macro.py` loses the FRED API and `fredgraph.csv` branches for the staged files this epic still writes (`M2SL` from sealed rows). `DTWEXBGS` is omitted with one stderr line: `DTWEXBGS is not on the gloomberb panel; dxy sibling CSV skipped`.

- [ ] **Step 4: Run**

```bash
PATH="$PWD/.venv/bin:$PATH" pytest -m unit \
  tests/dq/data/test_gloomberb_macro.py \
  tests/dq/indicators/test_macro_liquidity.py \
  tests/dq/test_export_sdca_macro.py \
  tests/dq/research/test_phase_tool_flags.py \
  tests/scripts/test_refresh_market_data_r2_macro.py -q --tb=short
```

Expected: pass.

- [ ] **Step 5: Commit** `feat(digiquant): drop eight macro series gloomberb does not serve`.

---

## Acceptance (issue #4794)

| # | criterion | proof |
|---|-----------|-------|
| 1 | Refresh / `fetch-macro` pulls the 23 series from Gloomberb and seals the existing R2 layout | PR 2 tests: `_fetch_macro("fred", ...)` calls `fetch_gloomberb`, keys stay `market-data/macro/fred__DGS10/...`. Core mirror still yahoo-only. |
| 2 | YAML / docs drop the 8 | PR 3 `test_manifest_matches_probed_panel` and the skill/dashboard edits. |
| 3 | `get_macro_series` still works for kept series | No signature change. Pointer prefix stays `fred`. Existing `tests/dq/test_mcp_market_data_backend.py` still passes. Dropped ids with a leftover pointer still return the last seal. |
| 4 | No `FRED_API_KEY` on this path | PR 2: runner `env` arrays, workflow env lines, CLI does not read the variable, `drop_fred_without_key` is not called. `rg FRED_API_KEY apps/digiquant-runner digiquant/src/digiquant/cli/prices.py scripts/refresh_market_data_r2.py` is empty. |
| 5 | History / rate-limit / terms notes, probe retained | This plan plus `scripts/probe_gloomberb_macro_panel.py` and its unit test. ARCHITECTURE states the 1000-row cap and the window-merge rule. |
| 6 | Plan before implementation | This file and the issue comment. |

Manual check after PR 2 deploys (operator, not CI): run the probe script once from a host that can reach `api.gloom.sh`. Expect exit 0. Then one `market-data-refresh` with the key unset. Artifact `fred_skipped` empty. Outcomes for `fred__DGS10` and `fred__M2SL` are `incremental`, `up-to-date`, or `full-repull`/`bootstrap`, not `history-only`. A `history-only` on a daily kept id fails the job, which is correct.

---

## Out of scope

- Re-implementing #4795. It is on `develop` (`01ef80df0`). PR 2 deletes the skip because the replacement writer does not need a key.
- Aliases for the 8 ids, including Yahoo `DX-Y.NYB` as a stand-in for `DTWEXBGS`.
- Deleting historical `fred__*` objects for the 8 ids.
- Paging `econ_series` past 1000 rows, or changing `EconSeriesInput`, until a follow-up proves a parameter.
- Rewiring `digifetch_price_history`, quotes, or Yahoo FX.
- Mirroring the panel into `macro_series_observations`.
- `digikey/`, live-trading, broker adapters.
- Putting a session cookie or any new secret on `digiquant-runner`.
- Editing generated OpenWiki pages.

---

## Self-review

- Issue acceptance 1–6 each map to a PR and a test command above.
- `#4796` `drop_fred_without_key` is called out so a wire that only changes `_fetch_macro` cannot ship while `main` still skips every `fred` series.
- Restatement cannot call `fetch_macro_full` for `source=="fred"` after the swap; the test asserts the pre-page row survives.
- `get_macro_series` is a read of `fred__*`. The plan does not rename keys and does not add a live Gloomberb call on the read path.
- Frozen sets are defined once. PR 2 and PR 3 both import them.
- No `TBD` parameters: limits are 60 / 16 / 8 / 4 and bootstrap 1000.
