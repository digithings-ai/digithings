## 3. API Surface

> Split out of [digiquant/ARCHITECTURE.md](../../ARCHITECTURE.md) (DIG-3399). Prose is unchanged. Relative links were adjusted for this directory.

### REST Endpoints

All endpoints bind on `127.0.0.1:8001` by default. Auth is enforced by `DigiAuthMiddleware` from `digikey.integrations`. The `/health` endpoint is public; all others require a valid digikey JWT with the appropriate scope.

#### Synchronous endpoints

| Method | Path | Auth Scope | Description |
|---|---|---|---|
| `GET` | `/health` | None | Legacy health check; returns `{"status": "ok", "service": "digiquant"}` (back-compat; prefer `/healthz`) |
| `GET` | `/healthz` | None | Liveness probe; returns `{"ok": true}` (auth-exempt, rate-limit-exempt; see AGENTS.md "Liveness vs status") |
| `GET` | `/strategies` | `digiquant:backtest` | List registered strategies (name, aliases, description, default_params) |
| `GET` | `/bars` | None (keyless) | OHLCV bars for dashboard charts (#4880); query params: `symbol` (required), `timeframe` (`1m`/`5m`/`15m`/`30m`/`1h`/`1d` default/`1wk`/`1mo`), `limit` (1–500, default 120). Returns `BarsResponse` (newest-last bars, `source: gloomberb`, `stale` + `delay_note`). See §3.1 |
| `GET` | `/check_drift` | `digiquant:backtest` | ADDM drift check for a strategy; query params: `strategy_id`, `baseline_run_id` |
| `POST` | `/run_backtest` | `digiquant:backtest` | Synchronous NautilusTrader backtest; returns `BacktestResult` |
| `POST` | `/run_optimize` | `digiquant:optimize` | Parameter optimization (grid/bayesian/random); returns `OptimizeResult` |
| `POST` | `/run_export` | `digiquant:backtest` | Export strategy config to artifact; returns `ExportResult` |
| `POST` | `/run_pipeline` | `digiquant:backtest` + `digiquant:optimize` | Full pipeline via internal LangGraph; returns `{trace, backtest, optimize, export}` |
| `POST` | `/v1/workflow` | `digiquant:backtest` + `digiquant:optimize` | Versioned alias for `/run_pipeline` |

#### 3.1 Keyless bars (`GET /bars`, #4880)

Display-only OHLCV for dashboard charts; feeds #4879 Vela wiring (dashboard
fetches keyless, passes bars to Vela's offline `data` option — no keyed
provider, no Pine/scripting).

- **Keyless:** auth-exempt via `digiquant_path_scopes` (`GET /bars` → `None`;
  every other method/path keeps its scope). Rate limit is the 30/min default.
- **Read-only:** implemented in `digiquant/bars.py::fetch_bars` over the
  **anonymous** Gloomberb `price_history` path — no session cookie, no API
  keys, no order/broker imports. Symbols normalize to uppercase (same
  convention as the orchestrator `_normalize_symbols`).
- **Timeframe/range:** `timeframe` is exactly the Gloomberb resolution vocab
  (`1m`…`1mo`); each maps to a contract-safe upstream range
  (`DEFAULT_RANGE_BY_TIMEFRAME`: `1m`/`5m`→`1W`, `15m`→`1M`, `30m`→`6M`,
  `1h`→`3M`, `1d`→`1Y`, `1wk`→`5Y`, `1mo`→`ALL` — each within its §5.2 cap).
  Unknown timeframes are 422 with no request (rejected, never clamped).
  The upstream read is tail-sliced to `limit` (1–500, default 120).
- **Contract:** `BarsBar{timestamp, open, high, low, close, volume?}` +
  `BarsResponse{symbol, timeframe, limit, count, bars, source="gloomberb",
  stale, delay_note}` (`models.py`). Carries no Sharpe/PnL/drawdown — no
  performance claims originate here.
- **Errors:** typed envelope → HTTP (`invalid_input`→422, `not_found`→404,
  `rate_limited`→429, anything else incl. kill-switch-disabled →502);
  transport exceptions →502, never a raw traceback.
- **Not a pipeline primary:** free-tier data may be delayed up to 15 minutes
  (`delay_note`) — this stays a chart-display read and must never feed
  backtest/optimize (the Gloomberb "enrichment only" rule). No MCP twin:
  `digifetch_price_history` already covers the agent surface.
- **Tests:** `tests/dq/test_bars.py` (offline — `httpx.MockTransport` into a
  real `GloomberbClient` via the `digiquant.bars._build_gloomberb_client`
  seam; never live HTTP).

#### Async job endpoints

| Method | Path | Auth Scope | Description |
|---|---|---|---|
| `POST` | `/backtest/start` | `digiquant:backtest` | Submit async backtest; returns `{"job_id": "..."}` |
| `POST` | `/v1/jobs/backtest` | `digiquant:backtest` | Versioned alias for `/backtest/start` |
| `GET` | `/backtest/{job_id}/progress` | `digiquant:backtest` | SSE stream: `start`, `heartbeat`, `done`, `error` events |
| `GET` | `/backtest/{job_id}/result` | `digiquant:backtest` | Final `BacktestResult` (202 if still running) |
| `GET` | `/v1/jobs/{job_id}/status` | `digiquant:backtest` | Job lifecycle: `running` | `completed` | `failed` |

#### Orchestrator endpoints (digigraph hub dispatch)

| Method | Path | Auth Scope | Description |
|---|---|---|---|
| `POST` | `/v1/orchestrator_tools` | `digiquant:backtest` | Return OpenAI-style tool manifest (16 tools: 11 digiquant + 5 dashboard policy-replay) |
| `POST` | `/v1/orchestrator_invoke` | `digiquant:backtest` + `digiquant:optimize` | Dispatch named tool by `tool` field in request body |

#### dashboard policy replay endpoints (#3011 / WP16.9)

Recommendation/read surfaces for offline policy replay evidence. Summaries and
artifact IDs only — no confidential fills/holdings/nav dumps. Running and
evaluating never activate production policy. Default path scope remains
`digiquant:backtest` (no digikey edits).

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/dashboard/policy_replay/run` | Register a replay run against a stored pair |
| `GET` | `/v1/dashboard/policy_replay/{run_id}` | Replay-run summary (fail closed) |
| `GET` | `/v1/dashboard/policy_comparison/{comparison_id}` | Comparison summary (IDs/status only) |
| `POST` | `/v1/dashboard/policy_gate/evaluate` | Evaluate immutable gate criteria (eligibility only) |
| `GET` | `/v1/dashboard/policy_gate/evaluations/{evaluation_id}` | Gate-evaluation summary |
| `POST` | `/v1/dashboard/policy_governance_decisions` | Authenticated human decision write (`request.state.digi_auth` → `AuthenticatedPrincipal`) — **not** on MCP |

Frozen dual-route aliases at `/v1/olympus/policy_*` remain registered (`include_in_schema=False`) so existing clients keep working; do not treat them as the canonical API.

### Rate Limits

Implemented as per-IP sliding window using an in-memory `deque` behind a `threading.Lock`. Override at runtime with `DIGI_DISABLE_RATE_LIMIT=1`.

| Path | Limit |
|---|---|
| `/run_backtest` | 10 requests / 60 s |
| `/run_optimize` | 10 requests / 60 s |
| `/run_pipeline` | 10 requests / 60 s |
| `/v1/workflow` | 10 requests / 60 s |
| `/v1/jobs/backtest` | 10 requests / 60 s |
| `/v1/orchestrator_tools` | 30 requests / 60 s |
| `/v1/orchestrator_invoke` | 10 requests / 60 s |
| All other paths | 30 requests / 60 s |
| `/health` | Unlimited |

### MCP Tools

The MCP server (`mcp_server.py`) listens on `127.0.0.1:8767` by default with `streamable-http` transport. Stdio transport is available via `--stdio` for Claude Desktop. Pipeline tools delegate to `service.py`; SDCA data/fit tools delegate to `sdca_mcp.py` (same JSON as FastMCP).

Gloomberb tools are registered under `gloomberb_*` only (programmatic extensions of the Gloomberb platform). The `digifetch_*` names in the table below are the internal dispatch keys, not a second MCP registration. `gloomberb_quote` is the live price read.

| Tool Name | Description |
|---|---|
| `digiquant_list_strategies` | Returns JSON array of registered strategies |
| `digiquant_run_backtest` | Runs Nautilus backtest; `symbols_json` is a JSON array string |
| `digiquant_run_optimize` | Runs parameter optimization (grid/bayesian/random). `strategy_name=sdca` is Stage B walk-forward (vs-flat-DCA). Freeze Stage A weights via `strategy_params` `*_weight` keys |
| `digiquant_export` | Exports strategy config to a target artifact |
| `digiquant_run_pipeline` | Runs the full LangGraph pipeline |
| `digiquant_fetch_coinbase_ohlcv` | Fetches OHLCV from Coinbase (CCXT) into the price-history cache. Default `start` is Coinbase BTC listing `2015-07-20` (ETH/SOL return from the first available Coinbase daily bar). Do not prefix-clip to 900 days. `timeframe`/`end`/`through_yesterday` widen beyond the daily-only default (a vendor `ccxt-mcp` server already covers full CCXT generality; prefer it for anything beyond this). Intraday timeframes write under `price-history/{timeframe}/` so ISO timestamps never overwrite the daily `{ticker}.csv` cache (#3944). |
| `digifetch_quote` | Latest quote for one listing via Gloomberb Cloud (`api.gloom.sh`, anonymous; **enrichment only** — free-tier data is delayed up to 15 minutes and is never a pipeline primary). Default-OFF behind `GLOOMBERB_ENABLED` (explicit opt-in re-enables); payload carries "Sourced from Gloomberb" attribution + `term.gloom.sh/?ticker=` deep link (#4069) |
| `digifetch_quotes_batch` | Batch quotes for 1–20 listings (Gloomberb Cloud, anonymous). Per-item `status`/stale preserved: a stale listing is a null quote + reason code, not a failed batch |
| `digifetch_price_history` | OHLCV bars for one listing. Resolution × range caps (spec §5.2): 5m→1wk, 15m→1mo, 1h→3mo, 1d→5y (default), 1wk→5y, 1mo→all-time; out-of-contract requests return typed `invalid_input` — rejected, never silently clamped. An explicit `start_date`/`end_date` window (ISO `YYYY-MM-DD`, mutually exclusive with `range`) bypasses the caps for long history — sent as `rangeKey=ALL` + `startDate`/`endDate` (live: 610 weekly bars back to 2015; #4100) |
| `digifetch_ticker_financials` | Quote, profile, fundamentals, statements, and daily price history for one listing. `extended_statements=true` requests the SEC-sourced extended history; statement rows type the common fields and preserve the rest |
| `digifetch_options_chain` | Options chain for one listing; `expiration` is epoch seconds (all expirations when omitted). Calls/puts normalize to a `side` field per contract; free-tier delay reported in `data.delay_note` |
| `digifetch_sec_filings` | SEC filings / filing documents / filing content (`/cloud/sec/*`). `what` selects `filings`\|`documents`\|`content`; documents/content need `cik` + `accession` from an earlier lookup. Anonymous (live-verified 200). Cross-check vs direct EDGAR, not a replacement |
| `digifetch_holders` | Holder records (session-gated). Requires `GLOOMBERB_SESSION_COOKIE`; without it the envelope data is a typed `auth_required` error and no request is made. `owner_type` filters client-side |
| `digifetch_analyst_research` | Analyst recommendation, price target, and rating actions (session-gated; typed `auth_required` without the cookie). `limit` caps the client-side action list |
| `digifetch_corporate_actions` | Dividends, splits, and earnings history for one symbol (session-gated; typed `auth_required` without the cookie), flattened to one `kind`-discriminated list |
| `digifetch_earnings_calendar` | Upcoming earnings dates for 1–20 symbols. **Yahoo-backed via `yfinance` — no Cloud route and deliberately NOT attributed to Gloomberb.** `horizon_days` bounds the window from today; fail-soft per symbol (throttled symbols land in `warnings`) |
| `digifetch_exchange_rate` | USD exchange rate for an ISO-4217 `from_currency` (the Cloud route is USD-based). The 15-minute delay is `data.delay_note`, kept distinct from `stale` |
| `digifetch_search` | Search listings across venues (anonymous). `limit` ≥1 is clamped to 10 client-side and flagged via `data.limit_clamped`; rows keep symbol/exchange so a caller can pick a listing before quote/history |
| `digifetch_news` | Aggregated market news headlines (anonymous). `feed` selects latest/top/breaking/ticker/sector/topic; `ticker` filters the ticker feed and adds a deep link; `story_id` fetches one story |
| `digifetch_econ_calendar` | Structured economic calendar (`/cloud/econ/calendar`, anonymous; #4110 phase 1). The route ignores `limit` (live probe: a fixed ~105-row window), so the tool takes **no parameters**; rows carry `date`/`time`/`country`/`event`/`actual`/`forecast`/`prior`/`impact`. Wire prints may be numeric or text (e.g. `"3.2%"`) and unknown fields are preserved as extras |
| `digifetch_econ_series` | FRED-style macro series observations + metadata (`/cloud/econ/series/{seriesId}`, anonymous). `limit`/`sort_order` (desc default) page the observations; a missing print (FRED `"."`) maps to null. `info` types id/title/units (null when absent); unknown metadata stays extras |
| `digifetch_yield_curve` | Treasury yield-curve tenors (`/cloud/econ/yield-curve`, anonymous). Points carry `maturity`/`maturityYears`/`yield`/`asOf`/`stale` (`yield` is a Python keyword, so the attribute is `yield_`); any stale tenor folds into the envelope `stale` flag |
| `digifetch_cds` | DTCC PPD CDS trade tape (`/cloud/credit/cds`, anonymous). `issuer` (≤200 chars)/`days`/`limit` filter the tape; `days` is bounded 1–90 **client-side** — an out-of-range value is a typed `invalid_input` and no request is made (the route would answer 400). Trade rows type the dissemination/notional/rate fields and preserve the rest |
| `digifetch_research_search` | Full-text research search across transcripts/news/filings (`/cloud/search`, session-gated). Requires `GLOOMBERB_SESSION_COOKIE`; HTTP 401/402 (or a missing cookie) is a typed `auth_required` with no request. `query`/`limit`/`offset` page the result; hits carry `docType`/`ticker`/`title`/`url`/`snippet`, and `data.pagination` types `total`/`hasMore`/`nextOffset`/`countCapped` (live-verified) |
| `digifetch_congress_trades` | **REFUSED on every digiquant surface** (5 U.S.C. 13107(c)(1)(B); DIG-1057) — not registered in any MCP scope, filtered out of the orchestrator manifest, and answered with a typed `tool_refused` envelope by `POST /v1/orchestrator_invoke`. Do not re-add it without Counsel's written clearance. The underlying route is US House disclosure trades (`/cloud/congress/house`, anonymous; `year`/`limit` filter the tape) and **its upstream is live, not failing** — probed 2026-10-05: `GET https://api.gloom.sh/cloud/congress/house?limit=3` → HTTP 200, `source: "house-clerk"`, `filingCount: 407`, `filingsParsed: 20`, with parsed trade rows in the body. That liveness is exactly why the tool is refused rather than left inert. Rows are not raw: they carry `party`, `committees`, `stateDistrict`, `memberName`, `owner`/`rawOwner`, `sourceUrl` and upstream-computed `returnSinceTx`/`returnSinceFiling`/`returnAsOf`, and the envelope returns sibling `members` and `tickers`. Client, normalizer, models and the `free` entitlement row are retained in-tree so the route can be restored without re-deriving the endpoint shape |
| `digifetch_transcripts` | Earnings-call transcripts (`/cloud/transcripts`, session-gated, **requires Gloomberb Pro**). Requires `GLOOMBERB_SESSION_COOKIE`; a free (email-verified) session answers a non-JSON `Pro plan required` body (HTTP 402 is the live status), mapped to a typed `pro_required` carrying the upstream text — never an empty success. Rows come from the upstream `calls` list (`companyName`/`callAt`/`webcastUrl`; the `transcripts` key is also accepted). Provide exactly one of `ticker` (list that listing's calls) or `transcript_id` (fetch one call by id from `GET /cloud/transcripts/{id}`; #4110 phase 4a). Adds a `term.gloom.sh/?ticker=` deep link; detail mode links only when the payload carries a ticker. |
| `digifetch_saved_searches` | The signed-in session's saved searches (`/cloud/search/saved`, session-gated; #4110 phase 4a). No parameters; a missing cookie is a typed `auth_required` with no request. Rows carry the saved-search id/name/query with unknown fields preserved (the live row shape stays probe-pending — the probed session returned an empty list). No deep link |
| `digifetch_statements` | Annual/quarterly statement rows (`/market/statements`, session-gated; live-verified 401 anon / 200 with cookie). `period` selects annual\|quarterly\|both; rows are sparse line items — `date`/`currency` plus a few typed fundamentals fields, with the long tail (hundreds of line items) preserved as extras. Adds a `term.gloom.sh/?ticker=` deep link |
| `digifetch_ticker_tweets` | Recent X/Twitter posts mentioning one ticker (`/news/tweets`, session-gated; #4110 phase 2). The upstream echoes `limit`/`hours` but applies neither (live-verified: 375 rows for limit=1; ~394 rows spanning ~13 days for hours=1), so the client drops rows older than `now - hours` when `hours` is given, slices to `limit`, and reports `total_available` + `truncated`. Rows carry author/metrics blocks and unknown fields stay extras. Adds a deep link |
| `digifetch_tweet_search` | Search X/Twitter posts by `query` (`/news/tweets/search`, session-gated). `query_type` is Latest\|Top; same client-side hours filter + limit slice and `total_available`/`truncated` reporting as the ticker feed. No single-listing deep link |
| `digifetch_venues` | Exchange venue metadata (`/market/venues`, anonymous; live-verified 137 rows). No parameters; rows carry `mic`/`name`/`title`/`country`/`timezone` plus session clock fields (`isOpen`, `timeAfterOpenSeconds`, `timeToOpenSeconds`, `timeToCloseSeconds`) |
| `digifetch_screener` | Market screener (`/market/screener`, session-gated, **requires Gloomberb Pro**). `category` is gainers\|losers\|most-active, `count` 1–50, `mode` cache-first\|refresh. A free session answers HTTP 200 `status=unsupported` + `reasonCode=PRO_REQUIRED` (or a 402 `Pro plan required` body); both map to the same typed `pro_required` without tripping the breaker. The Pro success payload is unobservable, so rows are typed from the TS plugin's `CloudMarketScreenerItem` (`rank`/`currency`/`tradeCount`/`high52w`/`low52w`/`dayHigh`/`dayLow`/`lastUpdated`/`dataSource`; no `marketCap`) with the envelope's `providerId`/`category`/`asOf`/`stale`/`items`; every field optional and extras open |
| `digifetch_13f_funds` | 13F fund lookup (`what`-discriminated, anonymous; live-verified for search/top/tickers). `search`→`/cloud/sec/13f/funds?name=` (rows `{name, CIK}`), `top`→`/cloud/sec/13f/topfunds?quarter=YYYYQn` (rows `{cik, name, period_of_report, pnl}`; a dashed quarter is a typed `invalid_input` before any request), `tickers`→`/cloud/sec/13f/tickers?tickers=A,B` (`{cusip, ticker, company_name}`), `holders`→`/cloud/sec/13f/holders?cusip=&period_of_report=` (`{cusip, periodOfReport, ciks[]}`; the upstream currently answers a proxied 4xx for every period format probed, mapped to non-retryable `invalid_input` without opening the breaker) |
| `digifetch_13f_holdings` | 13F filings/forms/holdings (`what`-discriminated, anonymous; live-verified). `filings` (`from`/`to` required, ISO `YYYY-MM-DD` validated client-side) and `forms` (`cik`) return SEC index rows; `form` (`cik` + `accession_number`) returns holding rows mapped to `issuer`/`shares`/`share_type` plus the voting-authority columns. `cik` is zero-padded to the SEC's 10-digit form and `accession_number` is normalized to the dashed `XXXXXXXXXX-YY-ZZZZZZ` form client-side (an undashed value passed through would silently return an empty set); `has_more` is computed from a full page (bare array, no continuation token); the upstream caps one form at 20,000 rows (`MAX_FORM_ROWS`). Upstream 13F rejections proxied as a 5xx with a `Forms13F 4xx` body map to non-retryable `invalid_input` without recording a breaker failure |
| `digifetch_shiller` | Robert Shiller's monthly valuation series (`/cloud/econ/shiller`, anonymous; live-verified ~1869 rows from 1871). Returns the most recent `limit` rows (default 240/20y, ≤2000) with `price`/`dividend`/`earnings`/`cpi`/`longRate` plus `cape` and `excessCapeYield` (Shiller's ERP); `total_available`/`truncated` report the client-side tail slice. Long-run reference data — monthly update cadence, not intraday |
| `digifetch_proxy_statements` | Executive-compensation proxies (`/public/proxies/{ticker}` + `/{year}`, anonymous open reads with no account or plan; live-verified). `what=list` lists every proxy for the ticker; `what=statement` returns one full proxy (comp tables, named executives, say-on-pay support, key figures) and requires `year` — the **proxy** (filing) year, not the fiscal year (AAPL's 2026 proxy reports fiscal 2025). Adds a deep link |
| `digifetch_filing_events` | Classified 8-K filing events (`/public/events/{ticker}?limit=`, anonymous; live-verified). Rows carry item codes/labels/kinds, materiality, the SEC document URL, named people (officer changes and similar), and a model reading (`read=true`) when the filing carried news; newest first. Adds a deep link. Cached/delayed — cross-check against EDGAR |
| `digifetch_risk_reports` | 10-K risk-factor reports, diffed year-over-year (`/public/risks/{ticker}` + `/{year}`, anonymous; live-verified). `what=list` lists report years with risk/group/word counts and an overview; `what=report` returns one year's extracted risk factors, groups, the added/removed/reworded diff against the prior year, and notes (requires `year`). Adds a deep link. Cached/delayed — cross-check against EDGAR |
| `digifetch_short_interest` | Biweekly short-interest settlements (`/market/short-interest?symbol=&years=`, session-gated; live-verified: 401 anon → 200 with cookie). `years` is 1–10 client-side (live: 1→24 points, 5→120, 10→209; 0/11/99 silently fall back to the 3-year window upstream). Points carry shares short, prior shares short, average daily volume, days to cover, change percent, and a revised flag. Adds a deep link. Exchange-reported data, delayed by reporting cadence |
| `digifetch_equity_diagnostic` | On-demand AI evidence review for one listing (`POST /research/equity-diagnostic`, session-gated; live-verified). `symbol`/`exchange`/`mode` (cache-first\|refresh); the first request per symbol answers HTTP 202 with a `pending` payload (`status=generating` + `retryAfterMs`) and retries eventually yield a report whose findings keep `observation` and `interpretation` separate. Free sessions only receive `access=preview`. The payload's own `status` field is not the market-envelope discriminator (`direct_payload`), pending payloads are **never** client-cached, and complete reports are cached normally. Adds a deep link. Model-generated reading of Gloomberb's data — not investment advice |
| `luxalgo_library_search` | Full-text search over the LuxAlgo Library, concepts + indicators (hosted LuxAlgo MCP `mcp.luxalgo.com/mcp`, anonymous; #4779 P0). `query` free text, `limit` 1–50. Rows carry kind/slug/name/family plus the canonical `url`/`md_url`. Research reference only: "Sourced from LuxAlgo Library" attribution + `source_url` on every payload |
| `luxalgo_library_get_concept` | One Library concept page by `slug` (e.g. rsi; anonymous). Returns slug/name/family/aliases, the canonical `url`/`md_url`, and `content_markdown`. Research reference only |
| `luxalgo_library_get_indicator` | One Library indicator's **metadata** by `slug` (anonymous). Metadata only — indicator source code is not exposed (CC BY-NC-SA license boundary). Research reference only |
| `luxalgo_library_list_concepts` | List Library concept pages (anonymous). `limit` 1–200. Research reference only |
| `luxalgo_library_list_indicators` | List Library indicator entries (anonymous). `limit` 1–200. Metadata only, no source code. Research reference only |
| `luxalgo_library_list_tags` | List Library tags (anonymous). No parameters. Research reference only |
| `luxalgo_library_list_families` | List Library indicator families (anonymous). No parameters. Research reference only |
| `luxalgo_library_get_family` | One Library indicator family by `family` name/slug (anonymous). Research reference only |
| `luxalgo_edge_symbols` | Hosted Edge Stats coverage (anonymous, #4844): symbols, session calendars, coverage windows, session counts, nightly build time. No parameters. Precomputed statistics only — no raw vendor bars |
| `luxalgo_edge_presets` | Hosted Edge Stats preset catalog (anonymous, #4844): gap fills, opening-range breakouts, day-of-week effects, and more. `category` narrows to one category; ids feed `luxalgo_edge_report` |
| `luxalgo_edge_report` | One precomputed Edge Stats result (anonymous, #4844): P(outcome \| conditions) with N, Wilson 95% CI, sample guards, first/second-half stability split, per-year counts. Every result carries the honesty disclaimer in `data.disclaimer` and envelope `warnings` |
| `luxalgo_trackers_datasets` | Market Trackers CC0-1.0 catalog (anonymous, #4844; two families limited — DIG-1464): row counts, freshness, years with data, ticker-searchability. `dataset` selects one dataset's field roster — read before composing filters |
| `luxalgo_trackers_latest` | Newest ingestion day's rows for one Trackers dataset (anonymous, #4844): `dataset` required, `ticker`/`text`/`where` narrow, `sort` newest\|oldest, `limit` 1–100, `offset` pages. Freshness/ad-hoc lookups only — never a pipeline primary |
| `luxalgo_trackers_ticker` | One ticker across every ticker-bearing Trackers dataset for one year (anonymous, #4844): `ticker` required, `year` 1900–2100, `limit` 1–25 per dataset. Ad-hoc lookups only — never a pipeline primary |

**LuxAlgo license boundary (#4845).** The 9th hosted tool,
`library_get_source_code`, serves indicator Pine source under CC BY-NC-SA and
is deliberately unwrapped: no source payload may be persisted (Chroma /
Supabase / `documents` rows) or rendered into paid surfaces (tearsheets,
briefs, chat answers). Enforcement is `data/luxalgo/license_guard.py` —
`LUXALGO_COMMERCIAL_LICENSE` opt-in flag (default OFF; only
`1`/`true`/`yes`/`on` enable), dispatcher runtime refusal with a typed
`invalid_input` envelope and no request while OFF, per-state attribution
(`commercial_license` + `license_state` on every Library payload), the
`source_code_violations` surface assertions (MCP full/read, read scope,
manifest, entitlements, schemas, research subset stay at 14 even when licensed;
only the dispatcher may add the 9th, and only with the license), and the
repo-wide code-reference scan. Guard halves: `tests/dq/test_luxalgo_license_guard.py`
(unit) + `scripts/check_luxalgo_license_boundary.py` (CI-adjacent). Unknown
`luxalgo_*` names (including a future source-code name) answer HTTP 400 at
`/v1/orchestrator_invoke` until a dispatch row exists. No Pine vendoring, no
procurement (owner-side).

**digiquant-web local gateway.** `apps/digiquant-web/gateway/live_gateway.py`
is a development-only, read-scope adapter from the static browser app to one
scrubbed stdio MCP child. It binds only `127.0.0.1`, accepts only exact loopback
HTTP origins, exposes a fixed probe table (no tool passthrough), and never passes
cookies or service keys to the child. The browser opts in with
`NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL`; `lib/gateway/gateway-client.ts` independently
requires both the page and configured gateway to be loopback before it fetches.
The LuxAlgo surface there is Library metadata search plus attribution only.
The marketing hero chart is LuxAlgo Vela (`@luxalgo/vela`) on the public
Coinbase feed: candles, volume, moving averages, and a cycling native overlay.
Any non-local binding, edge auth, or deployment remains a human-gated
network-exposure change.

| `digiquant_fit_btc_power_law` | Fits the SDCA BTC power-law (RAQQR) valuation rails from cached daily price history (`data/prices/history_cache.py`, not a bespoke fetch) and persists the coefficients to `strategies/sdca/btc_power_law_coefficients.json` (#1082) |
| `digiquant_build_sdca_risk_index` | Builds the SDCA `date`/`risk` parquet from a `RiskModel` + cached daily prices (`history_cache.py`, never a bespoke fetch) and writes it for `SdcaStrategy.risk_path` (#3168). `risk_model` selector: `btc_power_law` / `generic_valuation` / `rolling_z` (`sdca/providers.py`). Oscillators are computed from **that ticker's** OHLCV. `indicator_weights` JSON `{valuation, m2, rs_eth, dxy, weekly_rsi, weekly_macd, sma_band}` defaults to valuation=1 / extras=0 (published BTC charts unchanged). Macro extras need on-disk `m2_path` / `dxy_path` and/or cached `eth_ticker`. Returns `{path, row_count, date_start, date_end, null_risk_days}` or `{"error": ...}` |
| `digiquant_fetch_bitview_series` | Fetch Bitview/BRK on-chain `day1` series (`mvrv`, `asopr_24h`, `puell_multiple`, `rhodl_ratio`) into `data/onchain/bitview/` parquet. JSON API only (no HTML scrape). `nupl` is refused by default (monotone of MVRV); `allow_derived=True` opts a caller who understands the caveat back in. Upstream base URL is **fixed** (no caller `base_url`, SSRF guard #3944); the code-only seam is an injected HTTP session / allowlisted host. Fail-soft + timeout. Hosted bitview.space is optional / no SLA — a vendor `mcp.bitview.space` MCP server already exists; prefer it for general Bitview access. Coin Metrics community CC BY-NC is **not** fetched and must not be republished commercially. Refs #1086 |
| `digiquant_fetch_bgeometrics_series` | Fetch a single bitcoin-data.com (BGeometrics) metric by `startday`/`endday` into `data/onchain/bgeometrics/` parquet. Free tier is rate-limited; `token` (or `BGEOMETRICS_API_TOKEN`, sent only to the fixed bitcoin-data.com host) is sent as both `Authorization: Bearer` and `X-Bgapi-Token` (exact header name unconfirmed). `metric` is validated against `^[a-z0-9-]+$` (no path/query injection). No caller `base_url` (SSRF / env-token exfiltration guard #3944). Fail-soft. A vendor `mcp.bitcoin-data.com/mcp` server already exists; prefer it for general BGeometrics access. |
| `digiquant_fetch_coinmetrics_series` | Fetch a single CoinMetrics Community API metric for one asset (`asset`/`metric` must each be a single value, not comma-separated, and a safe slug matching `^[A-Za-z0-9_-]+$` — cache-path traversal guard #3947) by `start_time`/`end_time` into `data/onchain/coinmetrics/` parquet. `page_size`/`api_key` widen beyond SDCA's default free-tier keyless usage; upstream base URL is **fixed** (no caller `base_url`, SSRF guard #3944). Fail-soft. No vendor MCP server exists for CoinMetrics, unlike Coinbase/BGeometrics/Bitview — hence this tool and the catalog tool below carry more of the general-purpose surface in-house. CC BY-NC, research-only. |
| `digiquant_list_coinmetrics_catalog` | Discovery tool: lists available CoinMetrics assets/metrics from `/catalog-v2/asset-metrics` (optionally filtered by `asset`), so a caller can find a metric name before calling `digiquant_fetch_coinmetrics_series`. Returns the raw catalog payload. Upstream base URL is **fixed** (no caller `base_url`, SSRF guard #3944). Fail-soft. |
| `digiquant_get_trade_levels` | Causal ATR / swing-pivot / Donchian trade levels for a direction (READ scope, read-only — never sizes or places orders). Primary path is a caller-supplied `ohlc_json` array of OHLC bars; `ticker` is a non-blocking local-cache convenience. Returns `{pair, direction, entry{low,high,ref}, sl, tp_ladder[{r,price,src}], trail_policy, source_ref, computed_at}`. `source_ref` grammar: `computed:atr14@<asof>\|k=<k_eff>\|reg=<regime>\|br=atr\|pivot\|donchian\|piv=<width>\|rr=<floor>\|src=base`. Full-precision floats (never 4dp-rounded). Refs #137 |
| `digiquant_fit_sdca_weights` | Stage A cycle-window weight fit for an `SdcaAssetProfile` (`btc_v1` / `eth_research_v1` / `profile_json`), then `regularize_weights`. Not a second optimizer: Stage B is `digiquant_run_optimize` with `strategy_name=sdca` and frozen `*_weight` keys in `strategy_params`. Returns `{weights, regularized_weights, regularized_weight_params, score, ...}` or `{"error": ...}` |
| `digiquant_compile_research_portfolio` | digigraph product-graph dry path (#3415): compile research + portfolio LangGraphs with no LLM / no book write. Returns `{dry_run, graphs[], idempotency_key, ...}` via orchestrator_invoke |
| `digiquant_generate_slapper_tearsheet` | Runs the NautilusTrader backtest for the Slapper family and writes TV-style tearsheet JSON to the digiquant.io frontend. Delegates each strategy to `generate_tearsheets.run_strategy_isolated` (spawn-per-strategy, #1389 — a second in-process engine would SIGABRT the long-lived server); resolves calibrations file → Supabase (example only via `allow_example_calibrations`), accepts `signal_delay_days` (#1462), and returns `{"entries", "failures"}` with per-strategy errors as data. Does **not** write `index.json` (the CLI `main()` owns that) |
| `digiquant_validate_slapper_vs_tradingview` | Trade-level parity check of a Slapper strategy against a TradingView "List of Trades" CSV export |
| `dashboard_run_policy_replay` | Register a policy replay run (summary IDs only; never activates) |
| `dashboard_get_policy_replay` | Fetch a replay-run summary by `run_id` (fail closed) |
| `dashboard_get_policy_comparison` | Fetch a comparison summary (artifact IDs / status only) |
| `dashboard_evaluate_policy_gate` | Evaluate immutable gate criteria (eligibility only) |
| `dashboard_get_policy_gate_evaluation` | Fetch a gate-evaluation summary by `evaluation_id` |

`create_mcp_server(scope=...)` gates registration: `scope="full"` (default)
registers all 127 tools; `scope="read"` registers only the 113 dashboard-chat
reads (strategy list, price/macro reads, causal trade levels, `query_research`,
policy replay/comparison reads, gate reads + evaluations, the coinmetrics
catalog, the 14 luxalgo hosted reads (#4779 P0 Library + #4844 edge/trackers),
and the 89 `digifetch_*` Gloomberb
enrichment reads — every digifetch tool is read-scope, including the 13
write-shaped workspace/broker tools, which are inert by the Task 7 read-only
verdict, not by scope: read-scope membership is not a read-only guarantee).
`--scope` / `DIGIQUANT_MCP_SCOPE` select the scope; `host`/`port` live on the
`FastMCP(...)` constructor — `run()` takes transport only.

Human decision write (`record_policy_governance_decision`) is **not** an MCP tool —
only the DigiAuth HTTP boundary may record decisions. There is no
promote/activate/set-live/rollback-live tool on any surface.

#### In-process agent tool surface — `digifetch_*` (#4146)

Pipeline LLM agents (research analysts, portfolio manager) call the digifetch x
Gloomberb family in-process through
`src/digiquant/data/gloomberb/agent_tools.py` — no MCP hop:

| Surface | What |
|---|---|
| `DIGIFETCH_TOOLS` | The OpenAI function schemas, **generated** from `orchestrator_tools.build_orchestrator_tool_manifest()` (filtered to the names declared in `TOOL_ENTITLEMENTS`) so the MCP, manifest, and in-process surfaces cannot drift; each carries the entitlement note + top-level `entitlement` key |
| `EQUITY_TOOLS` / `MACRO_TOOLS` / `PM_TOOLS` | Curated per-phase subsets (`<= 16` names each — prompt budget, not capability). Equity/sector research phases get company facts + analyst views (`EQUITY_TOOLS`); macro gets rates/credit/long-run valuation (`MACRO_TOOLS`); analyst + direction share `PM_TOOLS` (quotes/news/analyst views + macro context) |
| `available_digifetch_tools(subset)` | Subset → schemas, **filtering rather than advertising**: returns `[]` when `GLOOMBERB_ENABLED` disables the family, and drops `session`/`preview`/`pro` names when `GLOOMBERB_SESSION_COOKIE` is unset. Same zero-HTTP *client* policy as MCP (#4099), but the two surfaces differ in shape: MCP registers gated tools and answers each call with a typed `auth_required`/disabled envelope, while this in-process list never offers a tool that can only error |
| `build_digifetch_tool_dispatcher(client=None)` | `(name, args) -> json_str`; validates args through each tool's Pydantic input model, calls the `GloomberbClient` method, and returns the §7 attribution envelope (deep link from the tool's symbol/ticker arg; the Yahoo-backed earnings calendar is not attributed). The `/v1/orchestrator_invoke` `digifetch_*` branch (#4097) calls the same dispatcher for hub dispatch |
| `build_gloomberb_client()` / `gloomberb_envelope_json()` | The shared env-keyed client factory (one pacing/cache/circuit-breaker client per `(GLOOMBERB_ENABLED, GLOOMBERB_SESSION_COOKIE)` pair, lock-guarded for parallel LangGraph nodes) and the envelope serializer; `mcp_server` imports both (moved here in #4146) |

Wiring: `research/phases/_node_factory.build_grounding(digifetch_tools=...)`
composes the subset with the Supabase `DATA_TOOLS` / `RESEARCH_TOOLS` executors
into one name-routing dispatcher; `SegmentNodeSpec.digifetch_tools` carries the
flag for the equity/sector (`EQUITY_TOOLS`) and macro (`MACRO_TOOLS`) phases, and
`portfolio/phases/portfolio_common._portfolio_grounding` (analyst + direction) passes
`PM_TOOLS`. deliberation stays digifetch-free (research-tools-only by policy
#2908; its evidence path is the bundle + amendment flow) and the legacy Phase 7D
path is unwired.

Gating: the family is default-OFF behind `GLOOMBERB_ENABLED`; an explicit opt-in (``1``/``true``/``yes``/``on``) re-enables it;
`available_digifetch_tools` applies that kill switch **and** the session-cookie
gate to the advertised list, so a pipeline LLM is never handed a digifetch tool
whose only answer is a typed disabled/`auth_required`/`pro_required` error. The
client still enforces both gates per call, and the MCP surface keeps registering
gated tools and returning those typed errors. The
`DIGIQUANT_RESEARCH_DATA_TOOLS` kill-switch removes the subset with the other
grounding tools; and because Gloomberb is **enrichment only** (delayed,
rate-limited), the subset attaches **only when a primary grounding executor
actually built** — a segment with no data/research tools degrades to tool-less
rather than arming a tool loop on delayed enrichment data alone. The client
cache/breaker mutations are lock-guarded (`threading.Lock`) for parallel nodes.

Research retrieval (`query_research`, #4436) is the unified search surface over
research documents + the book, replacing the retired generic `query_data` reader.
One toolkit at `dashboard/research_retrieval/` backs both the in-pipeline agents
and MCP: `search_research(...)` in `research_retrieval/queries.py` takes a typed
`dataset` enum (9 searchable datasets — `documents`, `daily_snapshots`,
`positions`, `nav_history`, `theses`, `thesis_vehicles`, `position_events`,
`portfolio_metrics`, `decision_log`) with `run_type`/`run_id`/`date_from`/
`date_to`/`document_key`/`segment`/`ticker`/`sector`/`subject`/`doc_type`/
`retrieval_phase`/`include_prior`/`as_of_date`/`limit`/`offset`/`full_content`
filters. `retrieval_phase` is the retrieval/blinding phase (one of
`RetrievalPhase`, validated — an unknown name errors instead of falling through
unblinded); it is not a `documents` column. No
raw-table or arbitrary-column surface exists. Look-ahead is impossible (the upper
window date is clamped to the effective `as_of`); the default is a single day
unless `include_prior` widens it to `date_from`. Every `documents` read is gated
by `research_document_allowed(retrieval_phase, key)` (phase-scoped blinding), and
portfolio datasets are gated by `portfolio_tool_allowed`. Archived
`documents.payload` bodies hydrate read-through from R2 (`_hydrate_archived_rows`);
`documents.content` is never archived. `content` is preview-truncated to 500
chars unless `full_content`. In-pipeline wiring:
`research/phases/_node_factory.SegmentNodeSpec.use_research_tools` /
`research_phase` (`build_segment_node`, deliberation gets the full toolkit;
`portfolio/phases/phase7d_pm._pm_tools` passes `direction`). MCP:
`digiquant_query_research` (read scope) — the `digiquant_query_data` registration
is removed.

#### MCP vs HTTP-only (#1185)

MCP tools above are the discoverable agent surface. They wrap `service.py` (and
SDCA helpers) — the same functions HTTP uses for the pipeline twin routes.
**HTTP-only** (no MCP twin; do not invent a tool for these without a new issue):

| HTTP route | Why not MCP |
|---|---|
| `GET /health`, `GET /healthz` | Liveness probes |
| `GET /check_drift` | ADDM operator diagnostic |
| `POST /backtest/start`, `GET /backtest/{id}/progress`, `GET /backtest/{id}/result` | Streaming / long-poll job API |
| `POST /v1/dashboard/policy_governance_decisions` | DigiAuth human decision write |
| Frozen `/v1/olympus/policy_*` aliases | Legacy dual-route; not canonical |

Orchestrator HTTP (`/v1/orchestrator_tools`, `/v1/orchestrator_invoke`) exposes the
same tool *schemas* as MCP for digigraph hub dispatch — not a second hidden
pipeline. The `digifetch_*` family dispatches through the shared in-process
`build_digifetch_tool_dispatcher()` (#4097), returning the §7 attribution
envelope under `data`; a declared-but-gated name without a session cookie
answers the typed `auth_required`/`pro_required` envelope (`ok: false` +
message at `error`, envelope preserved under `data`) instead of a 400.
Unknown tool names keep the `400 Unknown orchestrator tool` fallback.

The `digiquant_pipeline_delegate` tool is a second name in the orchestrator manifest (same function), used by digigraph's hub dispatch to alias the pipeline call.

#### MCP hosting — dedicated container (#3780 Task 8)

The market-data MCP server ships as its own image, `digiquant/Dockerfile.mcp`
(build context: monorepo root): `python:3.12-slim` + per-package COPYs
(workspace deps `digibase`/`digikey` first, mirroring `digiquant/Dockerfile`)
and `uv pip install --system -e "./digiquant[research,mcp]"`, entrypoint
`python -m digiquant.mcp_server` (FastMCP `streamable-http` on `:8767`). It
carries the `[research]`/`[mcp]` extras — never the backtest engine. The hosted
bind is non-loopback via `DIGIQUANT_MCP_HOST=0.0.0.0` /
`DIGIQUANT_MCP_PORT=8767` (code defaults stay `127.0.0.1:8767` for local runs).

Cloudflare wiring (`apps/digithings-stack-cloudflare/`): `DigiQuantMcpContainer`
beside `DigiStackContainer` (own `[[containers]]` image entry, `MCP_STACK`
binding, `v2` migration), routed by exact hostname (`mcp.digithings.ai`,
reserved) only — no workers.dev forwarding route ships. Single replica by design (`max_instances = 1`, one pinned
`MCP_CONTAINER_ID`): the read path assumes one replica (in-memory 900s TTL
keyed by `as_of` + manifest version; correctness never depends on the cache —
R2 is source of truth).

Networking/auth: public hostname `mcp.digithings.ai` is reserved, not enabled —
the `[[routes]]` entry stays commented until Worker-edge digikey JWT enforcement
lands. Caller auth is via digikey, scope `digiquant:backtest` (the default/read
scope in `digiquant_path_scopes()`; no new scope was minted — current MCP tools
are unauthenticated localhost). Enabling the route without that gate is a human
decision (new external network exposure).

Egress: the container needs `https://query1.finance.yahoo.com` (30d live overlap)
and `https://api.stlouisfed.org` (FRED macro overlap). Verified 2026-09-10 from
the operator host: `curl -sI https://query1.finance.yahoo.com` → HTTP 429
(Yahoo rate-limit, i.e. egress works — same retry/backoff 1s/2s/4s as the
refresh cron applies); `curl -sI https://api.stlouisfed.org` → HTTP 301 to the
API docs. Re-run both before first deploy; a 429 storm behind shared egress
means backing off the overlap window, not widening it.

Cold-start policy: `sleepAfter = "15m"` on the container class, so the container
may sleep after 15 minutes idle. A cold start only pays the FastMCP import,
never a data load. The daily `market-data-refresh` cron keeps R2 fresh and never
touches the container; once the custom-domain route is enabled it can be pinged
manually:
`curl -sS https://mcp.digithings.ai/mcp -H 'Accept: application/json'`.

Per-component secrets (`wrangler secret put`, never committed):
`GLOOMBERB_SESSION_COOKIE` (session-gated digifetch tools, #4260), and the four
R2 names `R2_ACCOUNT_ID` / `R2_BUCKET` / `R2_ACCESS_KEY_ID` /
`R2_SECRET_ACCESS_KEY` (same `digithings-archive` bucket as the checkpoint
archive). The read path is registry-read-only (registry inserts raise) so the
cron's `CORE_POSTGRES_URI` is deliberately NOT forwarded here.
`DIGIQUANT_MARKET_DATA_BACKEND` is passed through with no Worker-side default:
unset/empty keeps the library default (`supabase`); set it to `"r2"`
explicitly via env for the hosted path. `GLOOMBERB_SESSION_COOKIE` is forwarded
as container runtime env (#4260), so once the secret is set the gated digifetch
tools take the session-authenticated path instead of the zero-HTTP typed
`auth_required`; an unset/empty value preserves that `auth_required` behavior.
The operator path is in
[docs/ops/gloomberb-session-cookie.md](../../../docs/ops/gloomberb-session-cookie.md).

Owner applies the six secrets from `apps/digithings-stack-cloudflare/`
(`$VALUE` filled only in the operator's shell history — never in the repo;
`env -u` per the `CLOUDFLARE_API_TOKEN` trap noted in `wrangler.toml`):

```bash
printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put GLOOMBERB_SESSION_COOKIE
printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put R2_ACCOUNT_ID
printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put R2_BUCKET
printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put R2_ACCESS_KEY_ID
printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put R2_SECRET_ACCESS_KEY
```

#### Market-data reads: R2 (`DIGIQUANT_MARKET_DATA_BACKEND=r2`)

R2 is the market-data **read path** (#4013). History reads go through the
seam helpers in `research/data/queries.py` — `r2_backend_enabled()`,
`r2_close_rows(*, tickers, since, until)`,
`r2_close_rows_tolerant(*, tickers, since, until, context)`,
`r2_ohlcv_rows(*, tickers, since, until)`, `r2_manifest_seal()` — consumed by
the five ops scripts (`execute_at_open.py`, `fill-entry-prices.py`,
`refresh_performance_metrics.py`, `verify_nav_replay.py`,
`finalize_period_accounting.py`) plus the research/portfolio readers that
previously hit the Supabase market tables. Price-technicals reads are R2-only
since #4053 and expose `get_price_technicals_batch(*, client, tickers, lookback,
as_of)` — the phase entry point that reads the sealed manifest once for the
whole basket instead of once per ticker (#4600). `r2_close_rows` fails loud on a
ticker with no sealed generation; readers whose documented contract is to read
a missing ticker as "no signal" (`query_price_deltas`,
`commit_io._interval_price_returns`, `get_sector_relative_strength`) call
`r2_close_rows_tolerant`, which drops the absent tickers and logs them by name
(#4139). The flag lives in
`.github/digiquant-pipeline.yml` (loaded into `$GITHUB_ENV` by
`workflows/pipeline-digiquant.yml`) with per-step copies in the five
research-metrics step envs and the at-open job env; unset/empty keeps the
library default `supabase`, and both bodies coexist for rollback.

Freshness: reader-side `research/data/freshness.py::assert_market_data_fresh`
(seal ≤ 1 day, ≥ 100 price tickers; tested, no production caller yet) and
cron-side `data/prices/refresh_gate.py::staleness_gate` (seal ≤ 5 trading
days — breach keeps the prior objects serving, writes the manifest
`stale=true`, exits non-zero). Two Supabase market reads remain by design:
same-day execution (`d > seal` — `execute_at_open` / `fill-entry-prices`
price opens and fills from `price_history`; D3) and `FEDPROB/*`
prediction-market odds (`get_fed_rate_probabilities`; no R2 generation; D2).

`scripts/refresh_market_data_r2.py` also exits non-zero when any macro series
lands in a soft-fail mode (`history-only`/`error`), so the live fetch window has
to span at least one publication period of the series (#4588). No `FRED_API_KEY`
is read anywhere on this path (#4794): `source=="fred"` fetches the newest
anonymous Gloomberb `econ_series` page per kept series (`window_limit` by
cadence: 60/16/8/4; 1000-row tail on bootstrap, sealed with a `truncated` note)
and merges it into the existing `fred__*` generation, keeping sealed rows older
than the page. A same-seal revision takes the window-merge path, never a full
1990 re-pull. Only the 23 kept panel ids
(`data/prices/gloomberb_macro.py::KEPT_SERIES_IDS`) are selected; the 8 dropped
ids are never fetched and their `latest` pointers keep serving the last seal.
`digiquant prices fetch-macro` reads the same panel the same way (`--dry-run`
prints ids without a client; `--backfill` is a 1000-row tail, not 1990).
`LIVE_WINDOW_DAYS`
(45) assumes a daily series; a monthly FRED series (`M2SL`, `UNRATE`, `MANEMP`,
`CPIAUCSL`, `PCEPI`) legitimately has no new observation inside it — release lag
plus the pending release puts the newest month up to ~90 days behind the run — so
the window came back empty, `_fetch_macro` raised `empty live window`, and every
scheduled refresh was marked stale. Each entry in
`research/config/macro_series.yaml` may now declare a `cadence`
(`daily`/`weekly`/`monthly`/`quarterly`), which selects the window
(`_CADENCE_WINDOW_DAYS`: 45/45/120/240 days — weekly shares the daily constant;
there is no 60, and absent = daily is also the narrowest of the four). The widened window
then *contains* the series' seal row, so the live fetch is non-empty and the
existing benign `up-to-date` path covers it. Note what does **not** change: an
empty live window still returns `history-only` — `_fetch_macro` raises on empty
and the `except FetchError` arm maps it to the soft-fail mode — because an empty
window is genuinely ambiguous (a dead feed looks the same as a very slow one).
The fix is the window containing the observation, not a new benign-empty branch.
A series whose seal falls outside the widened window still fails the run, so a
genuinely dead feed is detected (though at the slower cadence: up to 120 days for
monthly, versus 45 before; weekly keeps the 45-day default because several weekly
publications already fit inside it). Contract tests:
`tests/scripts/test_refresh_market_data_r2_macro.py`. A cadence outside the map
raises `ValueError` rather than silently defaulting. Second-order effect of the
wider monthly window: a revision to a monthly print that is 45–120 days old is now
inside the window and takes the `_restated` path (a full-history re-pull) where it
used to be invisible; that is the intended sealing behaviour, at the cost of an
occasional extra re-pull.

The cadence exemption is per-series, so it also needs a whole-leg guard. `history-only`
on a slow-cadence series is exempt on its own (one series sitting out its release cycle
is not an outage), but a *total* macro-feed death made every outcome exempt at once:
`failed` came back empty, `staleness_gate` is only a date-gap check over the max
`as_of` that a whole-leg freeze does not move, and the run exited 0 claiming fresh with
the macro panel frozen at the last good seal (DIG-694 / DIG-981).
`_macro_leg_dead(outcomes, exempt)` suspends the exemption when **every** exempt
series is `history-only` at once (with a `> 1` floor, so a single-series manifest cannot
trip it), so the operator sees the `fred__*` ids in `artifact["failed"]`. Unanimity, not a
majority: `history-only` on a slow series has two causes — an exhausted 120/240-day
publication window, or a per-series vendor refusal — and `_fetch_macro` builds a fresh
client per series, so a rate-limit blip silences an arbitrary subset. A partial leg is
indistinguishable from that blip, and firing the gate on a healthy panel is how operators
learn to ignore it. `main` emits exactly one outcome per macro spec, so the exempt ids and
their outcomes always line up. Two known limits follow from the floor and the unanimity,
both accepted rather than half-solved by a magic constant: a manifest with a single exempt
series cannot trip the guard, and a partial leg stays exempt exactly as it did before this
guard existed. Suspending the exemption only ever *adds* names to `failed` — it never turns
a stale run fresh. A daily or `error` outcome is never exempt at any cadence. Staleness
flag only — no money, rate or weight arithmetic. Contract tests:
`tests/scripts/test_macro_death_is_not_silent.py`.

**What this guard alone does not cover.** It closes the unanimous `history-only` shape only,
and only over series the manifest actually declared. Read alongside the `_macro_as_of_stale`
age guard, which covers the other two:

| Shape | Why the guard cannot see it | Status |
|---|---|---|
| Partial leg (2 or 3 of 4 slow series dead) | indistinguishable from a rate-limit blip *while the silent series' seals are still inside their own windows*; a subset is not evidence of a mode, but each of them is evidence of its own age | accepted, by design **only while those seals are fresh**; DIG-2405 then names each one individually on its own age |
| Panel serving stale rows in-window | outcome is `up-to-date`, not a soft fail, so it never enters the reduction | closed by DIG-1137 |
| Single **slow-cadence** series in the manifest | the `> 1` floor counts exempt ids, not manifest size — an 8-series panel with one monthly series has a frozen slow leg and cannot trip it | closed by DIG-1137 + DIG-2405 (`_macro_as_of_stale`; the `> 1` floor stands) |
| Unreadable manifest | `_resolve_macro_specs` swallowed the exception and returned `[]`, so `exempt` was empty and the guard had no ids to reason about | **closed (DIG-1371)** — the resolver now returns a list carrying `manifest_error`; `main` reports it as a `macro-manifest-unreadable` `error` outcome *after* the equity leg has run (never a raise, which would abort before `refresh_universe`), so the run exits 1 with the cause in `failed` and `core_macro_mirror.skipped` names the manifest problem |

The `> 1` floor stands. A single-series manifest still has no leg to judge, and a single
silent series among several is not a mode-based death the leg test can see — the DIG-2405
decision below is that it *is* worth naming, but it is named by measuring the seal's age,
not by relaxing unanimity. Relaxing it would fire on every rate-limit blip.

DIG-1137 / DIG-2405 close the two sibling routes by measuring rather than trusting
`mode`. `_macro_as_of_stale(outcomes, macro_specs, run, already)` compares each macro
outcome's `as_of` against the run date, in calendar days, against the same
`_CADENCE_WINDOW_DAYS` bound the live fetch already used. It reads
`_MACRO_JUDGED_MODES` = the success modes (a vendor that keeps *answering* while it stops
*publishing* lands on `up-to-date`) plus `MODE_HISTORY_ONLY`, and skips `MODE_ERROR`
because that mode is never cadence-exempt and is therefore already loud. The
`history-only` inclusion is the DIG-2405 half: a retired slow series arrives in that mode
with an abandoned seal, the #4621 exemption forgives it on cadence alone, and
`_macro_leg_dead` needs unanimity over the whole exempt set, so one retired series among
live ones was named by nothing. Age separates the two cases that mode cannot, because an
empty window and a fresh seal are a quiet release cycle while an empty window on a
*stale* seal is a retirement. `already` keeps a series both guards reached named once. The
bound is each series' own window, not a widened threshold: a monthly series sealed 34 days
old is still quiet.

The unreadable manifest is still open. It needs its own fix — a loud outcome rather than an
empty spec list — because with no specs there are no ids for any of these guards to reason
about, whichever mode they read.

**Design record for the frozen-but-serving panel (DIG-1142).** Recorded here because the
summary above does not carry the reasoning. **Shipped** as `_macro_as_of_stale`; the shape
below is what it shipped as.

The gap is that `refresh_macro_series` returns `MODE_UP_TO_DATE` with `as_of=seal` whenever
the live window is non-empty but carries nothing newer than the seal. `up-to-date` is not in
`_SOFT_FAIL_MODES` and is not `history-only`, so the outcome never enters the reduction and
the run exits 0 claiming fresh. Two healthy paths reach that same shape: a same-day FRED
restatement (`MODE_FULL_REPULL`, `as_of=top2 == seal`) and an unchanged overlap that then
finds nothing new.

`_macro_as_of_stale(outcomes, macro_specs, run) -> set[str]`, defined next to
`_live_window_days` and called in `main` between the `failed` list and `stale = ...`:

- **Predicate.** For each macro series, take the declared cadence from `macro_specs`
  (ticker key is `f"{source}__{series}"`, matching `_slow_macro_exempt_ids`), resolve the
  window with the existing `_live_window_days`, and report the series when
  `(run_date - as_of).days > window`. Age against the series' own window, **never**
  `as_of == seal` and never `mode` — the two restatement paths above are healthy, so keying
  on either would fail a healthy panel.
- **Mode filter.** Success modes only (`MODE_UP_TO_DATE`, `MODE_INCREMENTAL`,
  `MODE_FULL_REPULL`). `history-only` and `error` are already `_SOFT_FAIL_MODES` and stay
  with `_macro_leg_dead`; an empty `as_of` is skipped rather than guessed.
- **No declared cadence** defaults to the 45-day daily window via `_live_window_days`,
  matching the live-fetch default rather than inventing a second one.
- **Calendar days, not trading days.** `_CADENCE_WINDOW_DAYS` is calendar days (45/120/240).
  `staleness_gate` (`digiquant/src/digiquant/data/prices/refresh_gate.py:49`) counts *open
  trading days* against `bound_trading_days=5`; reusing it per series would call a 120-day
  monthly series fresh after ~5 trading days. The file already has `_shift_days` for
  calendar arithmetic.
- **Per-outcome, composing with `_macro_leg_dead`.** `_macro_leg_dead` judges the leg
  (`history-only` on every exempt series at once); this judges one series' age. They are
  orthogonal, and the new names only ever *add* to `failed` — the guard never turns a stale
  run fresh. **The DIG-981 "a subset is not evidence" reasoning does not carry over to age.**
  That reasoning was about `history-only`, which has two causes (exhausted publication
  window vs. per-series vendor refusal) where a rate-limit blip silences an arbitrary subset,
  so a subset proves nothing. Age has one cause — the series is old — and it is measured, not
  inferred from a mode. A single frozen monthly series past its window is evidence by
  itself; the #4621 fuse already draws the line, fresh inside the window and loud outside it.
  At 34 days the seal is still inside the 120-day window and the run **should** exit 0.
- Staleness flag only. No money, rate or weight arithmetic, matching the other guards here.

**Known limits accepted for this guard.** Both are recorded rather than fixed, in the same
spirit as the two above:

| Limit | Why it stays |
|---|---|
| Undeclared cadence is judged at the 45-day daily window | the manifest is the source of truth; omitting `cadence` opts into the daily default, so a genuinely monthly series missing it goes loud at 45 days |
| The window is calendar days, not open trading days | deliberate, and consistent with `_CADENCE_WINDOW_DAYS`; reusing `staleness_gate` would fire ~5 trading days into a 120-day window |

**What this guard alone does not cover.** It closes the unanimous `history-only` shape only,
and only over series the manifest actually declared. Read alongside the `_macro_as_of_stale`
age guard, which covers the other two:

| Shape | Why the guard cannot see it | Status |
|---|---|---|
| Partial leg (2 or 3 of 4 slow series dead) | indistinguishable from a rate-limit blip *while the silent series' seals are still inside their own windows*; a subset is not evidence of a mode, but each of them is evidence of its own age | accepted, by design **only while those seals are fresh**; DIG-2405 then names each one individually on its own age |
| Panel serving stale rows in-window | outcome is `up-to-date`, not a soft fail, so it never enters the reduction | **closed (DIG-1142) — built as `_macro_as_of_stale`** |
| Single **slow-cadence** series in the manifest | the `> 1` floor counts exempt ids, not manifest size — an 8-series panel with one monthly series has a frozen slow leg and cannot trip it | closed by DIG-1137 + DIG-2405 (`_macro_as_of_stale`; the `> 1` floor stands) |
| Unreadable manifest | `_resolve_macro_specs` swallows the exception and returns `[]`, so `exempt` is empty and the guard has no ids to reason about | **open, pre-dates this guard** |

The `> 1` floor stands. A single-series manifest still has no leg to judge, and a single
silent series among several is not a mode-based death the leg test can see — the DIG-2405
decision below is that it *is* worth naming, but it is named by measuring the seal's age,
not by relaxing unanimity. Relaxing it would fire on every rate-limit blip.

DIG-1137 / DIG-2405 close the two sibling routes by measuring rather than trusting
`mode`. `_macro_as_of_stale(outcomes, macro_specs, run, already)` compares each macro
outcome's `as_of` against the run date, in calendar days, against the same
`_CADENCE_WINDOW_DAYS` bound the live fetch already used. It reads
`_MACRO_JUDGED_MODES` = the success modes (a vendor that keeps *answering* while it stops
*publishing* lands on `up-to-date`) plus `MODE_HISTORY_ONLY`, and skips `MODE_ERROR`
because that mode is never cadence-exempt and is therefore already loud. The
`history-only` inclusion is the DIG-2405 half: a retired slow series arrives in that mode
with an abandoned seal, the #4621 exemption forgives it on cadence alone, and
`_macro_leg_dead` needs unanimity over the whole exempt set, so one retired series among
live ones was named by nothing. Age separates the two cases that mode cannot, because an
empty window and a fresh seal are a quiet release cycle while an empty window on a
*stale* seal is a retirement. `already` keeps a series both guards reached named once. The
bound is each series' own window, not a widened threshold: a monthly series sealed 34 days
old is still quiet.

The unreadable manifest is still open. It needs its own fix — a loud outcome rather than an
empty spec list — because with no specs there are no ids for any of these guards to reason
about, whichever mode they read.

**Design record for the frozen-but-serving panel (DIG-1142).** Recorded here because the
summary above does not carry the reasoning. **Shipped** as `_macro_as_of_stale`; the shape
below is what it shipped as.

The gap is that `refresh_macro_series` returns `MODE_UP_TO_DATE` with `as_of=seal` whenever
the live window is non-empty but carries nothing newer than the seal. `up-to-date` is not in
`_SOFT_FAIL_MODES` and is not `history-only`, so the outcome never enters the reduction and
the run exits 0 claiming fresh. Two healthy paths reach that same shape: a same-day FRED
restatement (`MODE_FULL_REPULL`, `as_of=top2 == seal`) and an unchanged overlap that then
finds nothing new.

`_macro_as_of_stale(outcomes, macro_specs, run) -> set[str]`, defined next to
`_live_window_days` and called in `main` between the `failed` list and `stale = ...`:

- **Predicate.** For each macro series, take the declared cadence from `macro_specs`
  (ticker key is `f"{source}__{series}"`, matching `_slow_macro_exempt_ids`), resolve the
  window with the existing `_live_window_days`, and report the series when
  `(run_date - as_of).days > window`. Age against the series' own window, **never**
  `as_of == seal` and never `mode` — the two restatement paths above are healthy, so keying
  on either would fail a healthy panel.
- **Mode filter.** Success modes only (`MODE_UP_TO_DATE`, `MODE_INCREMENTAL`,
  `MODE_FULL_REPULL`). `history-only` and `error` are already `_SOFT_FAIL_MODES` and stay
  with `_macro_leg_dead`; an empty `as_of` is skipped rather than guessed.
- **No declared cadence** defaults to the 45-day daily window via `_live_window_days`,
  matching the live-fetch default rather than inventing a second one.
- **Calendar days, not trading days.** `_CADENCE_WINDOW_DAYS` is calendar days (45/120/240).
  `staleness_gate` (`digiquant/src/digiquant/data/prices/refresh_gate.py:49`) counts *open
  trading days* against `bound_trading_days=5`; reusing it per series would call a 120-day
  monthly series fresh after ~5 trading days. The file already has `_shift_days` for
  calendar arithmetic.
- **Per-outcome, composing with `_macro_leg_dead`.** `_macro_leg_dead` judges the leg
  (`history-only` on every exempt series at once); this judges one series' age. They are
  orthogonal, and the new names only ever *add* to `failed` — the guard never turns a stale
  run fresh. **The DIG-981 "a subset is not evidence" reasoning does not carry over to age.**
  That reasoning was about `history-only`, which has two causes (exhausted publication
  window vs. per-series vendor refusal) where a rate-limit blip silences an arbitrary subset,
  so a subset proves nothing. Age has one cause — the series is old — and it is measured, not
  inferred from a mode. A single frozen monthly series past its window is evidence by
  itself; the #4621 fuse already draws the line, fresh inside the window and loud outside it.
  At 34 days the seal is still inside the 120-day window and the run **should** exit 0.
- Staleness flag only. No money, rate or weight arithmetic, matching the other guards here.

**Known limits accepted for this guard.** Both are recorded rather than fixed, in the same
spirit as the two above:

| Limit | Why it stays |
|---|---|
| Undeclared cadence is judged at the 45-day daily window | the manifest is the source of truth; omitting `cadence` opts into the daily default, so a genuinely monthly series missing it goes loud at 45 days |
| The window is calendar days, not open trading days | deliberate, and consistent with `_CADENCE_WINDOW_DAYS`; reusing `staleness_gate` would fire ~5 trading days into a 120-day window |

#### Market-data R2 read path (#3780 Task 10)

`DIGIQUANT_MARKET_DATA_BACKEND=r2` routes the price/macro tools through
versioned R2 generations sealed at the manifest `as_of`, merged with a 30d
live overlap under settled-close semantics (`merge_history_live` +
`apply_settled_close(frame, as_of, sealed)` — full-path imports
`digiquant.data.prices.merge`, `digiquant.data.prices.r2_history`; the live
`as_of` bar is excluded unless sealed). Envelopes:
`{"as_of", "rows", "stale"}` for technicals,
`{"as_of", "series": {sid: {"latest", "window"}}, "stale"}` for macro.
Date-ascending rows; `as_of` before the first sealed bar serves `[]`.
Per-ticker vendor error entries fail soft (history-only rows) and loud
(`stale: true`). Contract tests: `tests/dq/test_market_data_asof.py`.

Stale glossary (two independent signals share the name):
`manifest.stale` (writer-side, Task 6 refresh cron — the seal's age at
generation time) vs the envelope `stale` (reader-side, evaluated per
request: seal >5 trading days behind `as_of`, or the live overlap carried
a per-ticker fetch error entry). They can disagree — a fresh manifest
served through a flaked live fetch reads stale here. Stale payloads are
never TTL-cached. Legacy token `fallback_used="supabase"` (preflight /
triage) keeps its vocabulary and now means "primary store fresh" — the
Supabase tables by default, the R2 seal under the cutover flag.

Value-parity contract (Task 7 premise guard → Task 10 definition): Task 1
goldens carry no `close` anywhere, so OHLC close parity is wiring-only
(synthetic closes round-trip the serving path). Macro is exact value
parity (no recomputation). Technicals parity is the golden-column subset
plus an exact round-trip vs `compute_indicators` on the same history
(±1e-9 parquet float tolerance). Future backfills own exact-OHLC parity:
record goldens WITH a `close` column, then promote the premise guard to a
real golden-value comparison.

Macro carve-out: migration `124_drop_market_data_tables.sql` is a **no-op**
(#3951) — its `price_history` + `price_technicals` DROPs stay commented out
because the on-cron Supabase readers were not yet migrated when it was ledgered.
The real drop ships as **`127_drop_market_data_tables.sql`** (#4053) — a new
numbered migration, never a re-edit of 124: `db-migrate.yml` records every
executed file in `digithings_schema_migrations` by name, so a re-edited 124 is
silently skipped. 127 drops the two views (`price_history_tickers`,
`public_price_latest`) before the two tables; every market read is R2/live-only
(see *Market-data reads: R2* above), and rollback is restore-from-generation +
replay, **not** a flag flip. `macro_series_observations` (fedprob/bitview) and
`trading_calendar` (calendar sync) are explicitly **not** dropped. The
post-cutover size gate (`data/cutover_gate.py`, `POST_CUTOVER_SIZE_GATE_MB=320`)
reads the `pg_database_size` total only: the ~172MB price-table saving lands
with 127 toward the ≈292MB target.

commit seal coverage: commit (`commit_cost_evidence.py`) reads the run-date session
bar but R2 seals through the manifest `as_of`; seal < run_date fail-softs
to the sealed tail. Live-fire checklist asserts seal coverage at commit time
(manifest `as_of` vs run_date) before sign-off.

Dispatcher matrix: all six data tools ride `build_data_tool_dispatcher`
with shared run-date-as-`as_of` threading; `get_fed_rate_probabilities`
is the documented Supabase exception (prediction-market odds have no R2
generation — exploding-client serves `Error:`). Executable re-verify is
the Task 7b dispatcher test
`tests/dq/test_market_data_parity.py:801`
(`test_dispatcher_matrix_rides_r2_backend`), which drives all six tools
through `build_data_tool_dispatcher`
(`tests/dq/test_market_data_parity.py:824`) and diffs each against the
direct-helper output.

Load comparison (`scripts/bench_market_data.py`, fake R2 store, TTL
cleared per sample, no network): Task 1 Supabase technicals p50 1413.2ms
/ p99 2078.8ms, macro p50 483.9ms / p99 863.7ms (n=3) vs R2 technicals p50
9.6ms / p99 11.8ms, macro p50 0.5ms / p99 0.9ms (n=100, as_of 2025-08-29)
— PASS on p99 <= 2x baseline AND p99 <= 800ms (see `docs/perf/baseline.json`).

Prod gate (human): Worker-edge digikey JWT enforcement (scope
`digiquant:backtest`) must land before production MCP use — not
implemented here. Owner actions: `CORE_POSTGRES_URI` is MISSING from GitHub
secrets (refresh cron + backfill need it); live refresh runs stay supervised
with the operator.

### CLI (`python -m digiquant` / `digiquant`)

Top-level click group in `cli/__init__.py`. Subgroups live under `cli/` (or dashboard for policy-replay). Pipeline commands call the same functions as HTTP/MCP via `service.py` where applicable.

| Command | Implementation | Notes |
|---|---|---|
| `backtest` / `optimize` / `export` | `cli/__init__.py` | Direct `run_*` entrypoints (same as HTTP handlers) |
| `strategy list` | `cli/strategy.py` → `service_list_strategies` | JSON; twin of MCP `digiquant_list_strategies` / `GET /strategies` (#160) |
| `strategy search <query>` | `cli/strategy.py` | Case-insensitive filter on name, aliases, description |
| `prices …` | `cli/prices.py` | OHLCV / technicals / macro cron surface |
| `onchain fetch-bitview` | `cli/onchain.py` | Bitview/BRK day1 → parquet + optional `macro_series_observations` (#1086) |
| `policy-replay …` | `dashboard/replay/cli.py` | Read-only governance summaries |

Still open from #160 AC: dedicated `indicator list` / `indicator compute` (closest today: `prices compute-technicals`; MCP indicator tools tracked in #152).

#### Slapper tearsheet pipeline

The BTC/ETH/SOL Slapper tearsheets published on digiquant.io are produced end-to-end by digiquant's own pipeline:

1. **Price** — `scripts/fetch_coinbase.py` pulls daily Coinbase OHLCV (CCXT) into `digiquant/data/price-history/<TICKER>.csv` (matches TradingView's Coinbase series). `generate_tearsheets.py` and `export_sdca_macro.py` default to the same directory (`DIGIQUANT_ROOT / "data" / "price-history"`). Do not point generate at repo-root `data/price-history` — that is a different tree (#3472).
2. **Backtest** — `scripts/generate_tearsheets.py` runs each strategy through the NautilusTrader engine, extracts round-trip trades from the positions report, and builds a TradingView-style percent-of-equity compounding equity curve + All/Long/Short stats, emitting `TearsheetData` JSON (`tearsheet_data.from_nautilus_run`) into `apps/digiquant-web/public/strategies/`. Each strategy's backtest runs in its **own spawned process** (#1389): NautilusTrader's Rust logging can only initialize once per process (`log::set_boxed_logger`), so a second in-process `BacktestEngine` aborts the interpreter with a logger re-init panic (SIGABRT). Isolation also contains any engine crash to its strategy — the script collects per-strategy success/failure, prints an OK/FAILED summary line per strategy, and exits non-zero if **any** strategy failed. On a partial failure, `index.json` keeps the prior entry for each failed strategy (so digiquant.io does not lose a live strategy card); a fully successful full run rewrites `index.json` as before.
3. **Validation** — `scripts/validation/pine_backtest.py` is a Pine-faithful replica of TradingView's fill model used as a parity oracle; `scripts/validation/compare_tv.py` matches our entries to a TradingView export (entry date + direction, broken down by signal family).

Structural settings (symbol, capital, sizing, 2018 trade window, precision) live in the **public** `strategies/settings.json`; proprietary indicator calibrations live in the **gitignored** `strategies/calibrations.json` (shape shown in `calibrations.example.json`). The `SlapperConfig.trade_start` gate mirrors Pine's `in_date_range` so warmup uses earlier bars while reported trades match the TradingView window.

**Strategy families (#3170).** Each settings entry may set `"strategy_type": "slapper" | "sdca"` (default `slapper`, so existing Slapper entries are unchanged). `btc_sdca` entries carry an `sdca` block (`preset`, `risk_model`, `long_only`, `initial_cash`, `indicator_weights`). Published `btc_sdca` is a **composite valuation index** (power law 1.0 + M2 0.5 + DXY 0.5 + weekly log-MACD 0.5 + weekly/monthly RSI 0.25; SMA band and BTC/ETH RS stay 0) with preset `btc_optimized` and `long_only: false` (sells enabled). Walk-forward `beats_flat_dca_oos` remains false — do not claim an OOS beat from the Stage 1 `curve_simulator` sidecar. For `strategy_type == "sdca"`, `run_and_write()` calls `materialize_sdca_risk_index()` on the **already signal-delayed** OHLCV frame, writes a temp `risk_path` parquet, and injects it (plus preset `curve_nodes`) through `get_strategy` overrides. The calibrations gate is skipped; tearsheet notes record the coefficients fit window and the preset. `get_strategy` / `run_nautilus` pass `trade_size` only when the config class declares it. SDCA's Nautilus venue is a **spot cash book** (`CurrencyPair` + `AccountType.CASH`); Slapper keeps the margin perpetual. The risk index is built on the full delayed cache; engine bars start at `trade_start` so lump/flat share that window. Real Coinbase coefficients are committed (#3173). `--push-supabase` is an **operator** step after a real Nautilus generate; agent environments do not push. This is the public strategy library (3-day signal delay), **not** broker live-trading.

**Tearsheet schema 1.1** (`tearsheet_data.SCHEMA_VERSION`) adds two back-compatible fields the renderer can opt into:

- `ohlc_bars: list[OHLCBar]` (`{t,o,h,l,c}`) — full-history candlesticks for the price chart. Note this spans the **entire** price series, while `equity_curve`/`trades` are scoped to the `trade_start` window — the renderer must not assume a shared x-axis. Defaults to `[]`; absent on 1.0 fixtures and on adapter paths with no bars.
- Per-trade signal type carried in `TradeRecord.entry_label` on the Nautilus path. `SlapperStrategy` records each entry's signal family in a metadata-only side-channel (`_signal_log`, keyed by `(entry_date, direction)`) — pure metadata, never fed back into a trade decision. `generate_tearsheets._entry_label` joins it onto round-trip trades and maps to the Pine display taxonomy (`MR Long`/`Trend Long`/`MR&T Long`/`Reversal Long` + Short variants), matching `scripts/validation/pine_backtest.py`. A join miss falls back to `""`.

**Tearsheet schema 1.3** (`tearsheet_data.SCHEMA_VERSION`, #3171) adds an optional
`dca: TearsheetDcaBreakdown | None` block for `kind == "dca"` books. Every existing
Slapper payload omits it and still validates. The block carries `vs_lump_pct`,
`vs_flat_dca_pct` (equal daily spend over the same window — the number that
isolates the signal from DCA's own averaging), `avg_cost_basis`,
`final_cost_basis_vs_price`, `capital_deployed_pct` / `capital_deployed_peak_pct`,
`units_accumulated`, and `buy_days` / `sell_days` / `no_trade_days` /
`avg_risk` / `avg_rate`. **Every `_pct` field in this block is a true percent
(×100)** — the same convention as `TearsheetData.net_profit_pct` and
`SdcaBacktestReport.vs_lump_pct`, and *not* the raw-fraction convention of
`SdcaBacktestReport.dca_max_drawdown_pct` (#2552 / #2549). For a DCA book,
`win_rate_pct`, `profit_factor`, `long`, and `short` are JSON `null` (not `0`)
so a renderer can tell "not applicable" from zero. Published numbers come from
Nautilus fills + mark-to-market equity (`sdca/dca_metrics.py`);
`SdcaBacktestReport` remains CI-only. The CI harness adds a `flat_dca_value`
column and matching report fields so tests can assert parity. Index extras
mirror `vs_lump_pct` / `vs_flat_dca_pct` / `capital_deployed_pct` for the
library card (#3172). Publish also copies #3168 diagnostic columns onto the
payload as optional series so the #3172 charts do not degrade: `rails`
(`{t,low,median,high}`), `risk_curve`, `cost_basis_curve`,
`capital_deployed_curve`, `lump_equity_curve`, `flat_dca_equity_curve`.
**Do not plot `capital_deployed_curve` as allocation** — it is
`(initial_cash - cash) / initial_cash × 100` and goes **negative after
sells**. Diagnostic charts use `allocated_pct_curve` =
`100 * units * price / (cash + units * price)` plus `fill_markers`
(`book_frac = |trade_usd| / portfolio` that day, from actual fills, not
curve-rate-sign `buy_days`/`sell_days`), `indicator_curves` (0–100 risk
scale per member; user-facing name for `valuation` is **power law**),
`indicator_weights`, and `curve_knees` (published `btc_optimized` buy
knee 25 / sell knee 70). The DCA block also carries `allocated_pct`
(final MTM allocated %, never negative) and `fill_buy_days` /
`fill_sell_days` (actual fills). Public UI KPIs show **MTM allocated**,
not capital deployed. `beats_flat_dca_oos` is copied from
`btc_optimized_provenance.json` onto the payload (currently **false**) —
full-sample Nautilus `vs_flat_dca_pct` is **not** this flag. Older 1.3
payloads omit those keys; the renderer reconstructs allocation and fill
dots from equity + capital_deployed + OHLC and treats a missing OOS flag
as "do not claim an OOS win". `current_signal` for a DCA book is today's
**risk, band, and remaining-book daily rate** (not long/short).
`strategy_signals.position` stays `long`/`flat` only because that table
is CHECK-constrained; the tearsheet UI reads `risk`/`band`/`daily_rate_pct`.
Slapper dumps omit these keys.

**Tearsheet schema 1.2** adds `signal_delay_days: int` (default `0`, back-compatible) — see the public signal delay below.

**Tearsheet schema 1.4** (`tearsheet_data.SCHEMA_VERSION`, #4828) adds the
honesty envelope to every `StatBlock`: `win_rate_n: int | None` (sample size
behind `percent_profitable`) and `win_rate_ci95: tuple[float, float] | None`
(Wilson 95% CI fractions). Both default to null, so 1.0–1.3 fixtures still
validate. Ported from LuxAlgo edge-stats `stats.ts` (MIT — code only, no
`data/`, no rebrand) into `digiquant.stats.honesty`: `wilson(k, n)`,
`apply_guards(n)` (warn 30 / refuse 10, identical to upstream),
`stability_split` (CI-overlap agree), Pydantic `HonestRate`, and the verbatim
disclaimer (`DISCLAIMER`). Every HTML tearsheet win-rate surface renders N +
95% CI via `format_honest_rate` — categorized/full/risk stats tables, the KPI
strip (thresholds act on the CI lower bound, not the point estimate), and the
win/loss donut, whose `k` is caller-counted from realized **round trips**
(`count_winning_trades(realized_pnls_series)`, counting `PnL > 0`) while its `n`
is the **fill** count `num_trades` — so the pair is not a like-for-like sample,
and the donut must never fall back to `round(rate * n)` as an observed count).
Tests: `tests/dq/test_honesty.py` (upstream golden vectors),
`tests/dq/test_tearsheet_honesty.py` (per-surface N + CI assertions).

**Model versioning for `BacktestResult` (DIG-845 / L3).** The clause that stood
here — "`BacktestResult` is untouched, so no model versioning was needed" —
was true of the tearsheet 1.4 work and stopped being true once the honesty
envelope reached the result model, so it is reworded here rather than dropped.
Per `AGENTS.md` § Pre-Flight ("Confirm `BacktestResult` Pydantic model is
unchanged or versioned if modified"), the decision is recorded: **additive,
back-compatible, no version bump.** L3 adds exactly two fields to
`models.BacktestResult`, both defaulting to an empty state —
`honest_rate: HonestRateBlock | None` (default `None`) and
`honest_rate_by_symbol: dict[str, HonestRateBlock]` (default `{}`) — so every
payload that validated before still validates, and a consumer that has never
heard of the envelope reads exactly what it read before. `num_trades` also
gained a sharper description on the same leaf (a **fill** count, and explicitly
*not* a win-rate denominator — `honest_rate.n` is the denominator), which is a
description change and not a type or semantic change. No published surface
depends on the old wording, so no migration, no `SCHEMA_VERSION` bump and no
consumer notification are required. Consumers that want the envelope read
`honest_rate`; they must never synthesize one from `num_trades` or from
`round(rate * n)`.

Existing published fixtures stay at older schema versions (no `ohlc_bars`, blank `entry_label`, no `signal_delay_days`) until regenerated, so consumers must tolerate all versions.

**Public signal delay (#1462).** The public tearsheets lag reality by **3 calendar days** ("backtested strategies running live — signals delayed 3 days") to protect strategy IP: on a single-asset long/flat strategy a current equity curve trivially leaks the live position. The mechanism is an **end-date shift, not redaction** — `generate_tearsheets.py --signal-delay-days N` truncates the OHLCV frame (`apply_signal_delay`, cutoff = newest cached bar minus N calendar days) *before* the backtest, so the entire tearsheet is generated as if run N days ago. Every artifact (equity curve, drawdown, trade log, open-position state, headline metrics, `period_end`) is self-consistent by construction; there is no per-field redaction logic to get wrong. The lag is declared honestly: the static JSON, the `index.json` entry, and the `strategy_tearsheets` metrics all carry `signal_delay_days`, and a payload note states the as-of date. `generated_at` stays the true generation timestamp (the delay is marketed openly, not hidden). Default is `0` (exact no-op) for internal/undelayed runs; the scheduled pipeline (`pipeline-digiquant-tearsheets.yml`) passes `--signal-delay-days 3`. Side effect: the `_PUBLISHED_BASELINE` drift warning compares exact trade counts, so a trade opened within the delay window can transiently warn — informational only. Tests: `tests/dq/test_tearsheet_signal_delay.py`.

**digiquant.io consumption** — the landing page, strategy library (`/strategies`), and tearsheet views read **live from Supabase `strategy_tearsheets`** at runtime (#1069): the client fetches the row via the shared anon browser client (`apps/digiquant-web/lib/live/`), so a fresh nightly upsert updates the site with **no rebuild or redeploy**. The static-JSON artifacts under `public/strategies/` were removed. Build-time still needs the *route list* (`generateStaticParams` in `app/strategies/[id]/page.tsx` hardcodes the three Slapper slugs **plus `btc_sdca`**); `dynamicParams: false` 404s any other id. Homepage `StrategySuite` lists the same four. Public names are **asset then type**: `btc_sdca` is **BTC-SDCA**; the Slapper books are **BTC L/S**, **ETH L/S**, **SOL L/S** (Slapper `enable_short` + net-short + BTC reversal flip — a long/short book, not RS). The library filters by public type (All / SDCA / L/S; RS is reserved on the enum). The Charts **Indicators** tab is SDCA-only (`showsIndicatorsTab` / public type `sdca`) — L/S P/L books never get that tab, even if a payload carried unused series. Public KPIs: total return, max drawdown, vs buy-and-hold (lump), MTM allocated. **vs-flat DCA is not a public comparable** (`flat_dca_mark_to_market` spends remaining cash equally each day and is fully deployed by the last bar; keep the number on the payload). Honesty (`beats_flat_dca_oos` false, backtest only, 3-day delay) lives in notes, not title chips. The primary chart is allocation + sized buy/sell fills, plus today's remaining-book signal. Operator go-live is `generate_tearsheets.py --strategy btc_sdca --signal-delay-days 3 --push-supabase` from a tree whose `settings.json` includes `btc_sdca` (real Nautilus backtest; no hand-inserted metrics). Nightly `pipeline-digiquant-tearsheets.yml` now stages `M2SL.csv` / `DTWEXBGS.csv` beside the Coinbase cache (#3453) so those composite weights are not silently dropped. The job still checks out `main` (#1626) — a family is unpublished until its settings entry is on main. Agents do not push.

Regenerate only when calibrations are available from **one** of:

1. **Local file** — `digiquant/src/digiquant/strategies/calibrations.json` (gitignored)
2. **Supabase** — `strategy_calibrations` table (service-role read; upload via `scripts/sync_strategy_calibrations.py`)

Without real calibrations, `SlapperStrategy` falls back to `calibrations.example.json` placeholder values and produces **wrong** trade counts (e.g. ~264 BTC trades instead of ~79). `generate_tearsheets.py` exits unless you pass `--allow-example-calibrations`.

**Daily pipeline (intended):**

```bash
python digiquant/scripts/fetch_coinbase.py --through-yesterday
python digiquant/scripts/export_sdca_macro.py
python digiquant/scripts/generate_tearsheets.py --from-supabase --push-supabase --signal-delay-days 3 --cache-dir digiquant/data/price-history
# No git commit — the DB is the delivery; the site reads strategy_tearsheets live.
# One-shot BTC-SDCA only: add --strategy btc_sdca (skips Slapper calibrations).
```

`--from-supabase` loads fitted params from `strategy_calibrations`. `--push-supabase` upserts the **full tearsheet payload** into `strategy_tearsheets.metrics` — the complete `TearsheetData` (headline metrics, equity/drawdown curves, OHLC bars, trades) plus a derived `current_signal` (position / last signal date / last price) and the index extras (`label`/`kind`/`avg_trade_pct`) — and refreshes the normalized `strategy_signals` row. digiquant.io reads that one anon-readable row live, so updating it updates the site with no deploy. The job (`pipeline-digiquant-tearsheets.yml`) is fetch Coinbase → stage SDCA macro CSVs → generate `--push-supabase --signal-delay-days 3 --cache-dir digiquant/data/price-history`, no repo write. Phase 2 of #4761 runs that sequence as digiquant-runner command `tearsheets` (digithings-cron `12 0 * * *`). The workflow stays `workflow_dispatch` and has no `schedule`. Coinbase fetch keeps `uv run --frozen --with ccxt`. `export_sdca_macro.py` runs only when that file is in the image. The explicit `--cache-dir` keeps the job correct while the image is pinned to `main` (#1626) even if `DEFAULT_CACHE` on that ref lags. Targets are every `settings.json` strategy (L/S Slappers + `btc_sdca`). Push upserts the public `strategies` catalog row first — `strategy_tearsheets.strategy_id` FKs that table, and SDCA was never inserted by the Slapper-only calibrations sync.

**One-time upload** (after optimizing in TradingView):

```bash
# Credentials: CORE_SUPABASE_* or legacy SUPABASE_URL + SUPABASE_SERVICE_KEY
# (research local runs: digiquant/src/digiquant/research/config/.env)
cp /path/to/your/calibrations.json digiquant/src/digiquant/strategies/calibrations.json
python digiquant/scripts/sync_strategy_calibrations.py --verify
python digiquant/scripts/verify_strategy_calibrations_rls.py
```

The separate `pipeline-digiquant-prices.yml` job owns `position_events` writes at the
market open and the surviving macro ingest; price/technicals ingest moved to the R2
refresh (`pipeline-market-data-refresh.yml`) and migration 127 dropped the Supabase
`price_history`/`price_technicals` tables (#4053). Phase 1 of #4761 moves those
clocks onto digithings-cron `kind: container` → the private digiquant-runner
Worker (`docs/ops/digiquant-runner.md`). The market-data workflow keeps
`workflow_dispatch` and has no `schedule`. It does
**not** regenerate these public tearsheets. Two UTC crons cover New York daylight
and standard time. `market_open_gate.py` selects the season-correct cron and keeps
it valid after the open even when GitHub delivers it late, while rejecting the
wrong-season duplicate and pre-open execution.

Each `index.json` entry carries a `kind` slug (`long_short`, `long_only`, …) from `settings.json` for library filters as the catalog grows.

---

