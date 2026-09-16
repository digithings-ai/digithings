# digifetch × Gloomberb — scoping and design

> **For agentic workers:** this is a scoping/design spec, not an implementation
> plan. It ships no implementation code and merges no new dependency. Read the
> whole document before acting on it. The acceptance criteria for the follow-up
> implementation live in issue [#4069](https://github.com/digithings-ai/digithings/issues/4069).

- **Date:** 2026-09-12 (issue) · 2026-09-15 (source + live-wire validation)
- **Status:** draft — revised after four fresh-context reviews (see §3.2, §11)
- **Issue:** [#3927](https://github.com/digithings-ai/digithings/issues/3927)
- **Validated against:** `gloom-sh/gloomberb` `0.13.3` (shallow clone, MIT) and
  eight anonymous live probes of `https://api.gloom.sh` (2026-09-15)

Author decisions (2026-09-15, verbatim): add **news as a 13th tool**; support a
**session cookie from day 1** so the gated tools work once a free Gloom Cloud
account is signed in; **default the tools ON** behind a kill switch. The
requester's original goal was an external integration — link digiquant tearsheets
and stock pages to Gloomberb pages, and fetch headlines and quotes through
digifetch, clearly attributed as sourced from Gloomberb.

---

## 1. Goal and scope

Evaluate consuming Gloomberb's `AssetDataProvider` surface from digithings and
decide the integration shape. **In scope:** validated capability table (§3), a
decision with trade-offs (§4, heading kept as `## Decision`), a 13-tool MCP
contract (§5), a data-source inventory with per-source paths (§6), attribution
and external-link behavior (§7), the dashboard-page evaluation (§8), the human
gate (§9), licensing (§10), risks (§11), and the follow-up outline (§12).
**Out of scope:** implementation (tracked in #4069), pipeline rewiring,
embedding `term.gloom.sh`, and any change to `digiquant/AGENTS.md`.

## 2. Background

| Fact | Value |
|------|-------|
| Upstream | `gloom-sh/gloomberb` — "Finance terminal, in your terminal." |
| License | MIT, `Copyright (c) 2026 Gloomberb Contributors` (LICENSE:15-17 adds an attribution-appreciation paragraph — see §10) |
| Version / runtime | `0.13.3`; Bun `1.3.11` (`package.json`); CLI shebang `#!/usr/bin/env bun` |
| Surfaces | TUI/desktop app, hosted terminal `term.gloom.sh`, JSON CLI, plugin system |
| Data stack | Gloom Cloud (`api.gloom.sh`, priority 100) → Yahoo fallback (in-process) → SEC EDGAR → FRED/Treasury; Cloud upstream is mostly Yahoo (`source: "yahoo"` observed live) |
| Auth model | Anonymous cookie-less access to the **ungated** routes (`/market/quote`, history, financials, options, search, FX; `/news`); holders/analyst/corporate-actions under `/market/*` answer **401** anonymously; client-side `requireVerifiedSession()` gates filings/holders/analyst/actions (six call sites, `index.ts:405-461`), but **SEC routes are not server-enforced** (§3.2) |
| Free tier | Rate-limited, market data delayed up to 15 minutes (`dataSource: "delayed"`, `delayMinutes: 15`); Pro realtime |
| Framing | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` on `term.gloom.sh` — embedding impossible (§8) |

## 3. Capability validation

The 14 issue-named methods, validated field-for-field against
`src/types/data-provider.ts`, `src/types/financials.ts`,
`src/sources/gloomberb-cloud/index.ts`, and live wire probes:

| Method | Cloud-backed? | Live anon? | Wire endpoint | Tool |
|--------|---------------|-----------|---------------|------|
| `getQuote` | yes (`index.ts:315`) | 200 | `GET /market/quote?symbol=&exchange=` | `digifetch_quote` |
| `getQuotesBatch` | yes (`:341`) | 200 | `POST /market/quotes/batch` | `digifetch_quotes_batch` |
| `getPriceHistory` | yes (`:472`) | 200 | `GET /market/history?symbol=&interval=&rangeKey=` | `digifetch_price_history` |
| `getTickerFinancials` (+Batch) | yes (`:261`) | 200 | `GET /market/financials`, `POST /market/financials/batch` | `digifetch_ticker_financials` |
| `getOptionsChain` | yes (`:530`) | 200 | `GET /market/options?symbol=` | `digifetch_options_chain` |
| `getSecFilings` / `…Documents` / `…Content` | yes (`:404`) | **200 anon** | `GET /cloud/sec/filings`, `/cloud/sec/filing/documents`, `/cloud/sec/filing/content` | `digifetch_sec_filings` (one tool, `what` discriminator) |
| `getHolders` | yes, client-gated (`:443`) | **401** | `GET /market/holders` | `digifetch_holders` |
| `getAnalystResearch` | yes, client-gated (`:452`) | **401** | `GET /market/analyst` | `digifetch_analyst_research` |
| `getCorporateActions` | yes, client-gated (`:461`) | **401** | `GET /market/corporate-actions` | `digifetch_corporate_actions` |
| `getEarningsCalendar` | **no** — Yahoo-only (`yahoo-finance.ts:402`) | n/a | no Cloud route; use digiquant's `yfinance` stack | `digifetch_earnings_calendar` (Yahoo-backed) |
| `getExchangeRate` (+Snapshot) | yes (`:381`) | 200 | `GET /market/exchange-rate?fromCurrency=` | `digifetch_exchange_rate` |
| `search` | yes (`:397`) | 200 | `GET /market/search?q=&limit=` | `digifetch_search` |
| news provider (`:586-624`) | yes, ungated | 200 | `GET /news?feed=…`, `GET /news/{id}` | `digifetch_news` |

### Validation

Discrepancies vs the paraphrased summary in #3927 that this spec corrects:

1. **Caps.** The issue's contract caps (`5m→1wk`, `15m→1mo`, `1h→3mo`,
   `1d→5y` default) match the *base* defaults in `src/time-series/resolution.ts`
   (162-167). The Cloud provider declares wider support
   (`CLOUD_RESOLUTION_SUPPORT`, `index.ts:60-69`: 1m→1W, 5m→1M, 15m→3M, 30m→6M,
   1h→1Y, 1d→5Y, 1wk→5Y, 1mo→ALL), but that table is a **client-side
   declaration**, not a wire guarantee — validate against live responses (§3.2).
2. **Gating.** The six `requireVerifiedSession()` call sites are client-side
   checks. Server behavior differs: SEC filings answered **200 anonymously**
   live, while holders/analyst/corporate-actions answered **401** (§3.2). Note
   also that earnings is not on Cloud at all.
3. **Tool count.** The issue's AC3 test greps for 12 tool rows; the revised
   contract has **13** (news added by author decision 2026-09-15; the filings
   triad collapses to one tool with a `what` discriminator). Every one of the 14
   issue-named methods still maps to a named tool — see §5.1 — so the count test
   is superseded, not the coverage.
4. **Not a unique source.** Cloud's quote/history upstream is Yahoo — the same
   endpoints digiquant already reaches via `yfinance`. Cloud adds shaping,
   aggregation, and news enrichment, not new raw coverage.
5. **`bunx gloomberb api list --json` diff not run.** Bun is absent from the
   authoring and review environments; this step is carried as an open item in
   §12 (spike) before freezing tool models. It does not change the decision.
6. **Endpoint map.** The issue's summary implies a single `/cloud/*` surface;
   the real map is three families — `/market/*` (quotes, history, financials,
   options, search, FX, holders, analyst, actions), `/news`, and `/cloud/*`
   (SEC, econ, transcripts, search, 13F).
7. **1wk range.** The issue's cap table promises all-time for `1wk`; a live
   anonymous probe returned 29 weekly bars (2026-02-23 → 2026-09-07) for
   `rangeKey=ALL` — the server truncates. A direct HTTP client has **no Yahoo
   fallback**, so the contract caps `1wk` at **5 years** (§5.2) and records the
   truncation as a spike item.

### 3.2 Live wire verification (2026-09-15, anonymous, no cookies)

| Probe | Result |
|-------|--------|
| `GET /market/quote?symbol=AAPL` | 200; envelope `{status, data, asOf}`; `dataSource: "delayed"`, `providerId: "gloomberb-cloud"`, `stale: false`, bid/ask, pre-market fields |
| `GET /market/history?symbol=AAPL&interval=1week&rangeKey=ALL` | 200; 29 bars (2026-02-23T00:00:00.000Z → 2026-09-07T00:00:00.000Z); bar dates are ISO datetimes, not date-only |
| `GET /market/options?symbol=AAPL` | 200; `calls`/`puts` arrays; `expiration` in epoch **seconds**; 23 expiration dates |
| `GET /market/holders?symbol=AAPL` | **401** `{"message":"Unauthorized"}` |
| `GET /cloud/sec/filings?ticker=MSFT&limit=1` | **200 anon**; `{filings:[…], hasMore, nextOffset}` with `acceptedAtRaw`, `primaryDocumentUrl` |
| `GET /news?limit=1` | 200; item keys include `headline`, `summary`, `primarySource`, `primaryUrl`, `sentiment`, `sectors`, `scores`, `tickerLinks`, `topic`, `firstSeenAt` — no `publishedAt`/`url`/`tickers` |
| `GET /market/search?q=apple&limit=10` | 200; multi-venue listings; server honors `limit` |
| `GET /market/exchange-rate?fromCurrency=EUR` | 200; `data.source: "yahoo"`, `delayMinutes: 15`, `stale: false` |

## Decision

**Recommended approach: (c) — a Python HTTP client against `api.gloom.sh`,
built on `digifetch` transport primitives.** "Chosen approach" is (c) with (d)
as the documented fallback.

| Approach | Verdict | Trade-offs |
|----------|---------|------------|
| (a) CLI shell-out (`bunx gloomberb …`) | **Rejected** | Requires a Bun runtime in the service image; subprocess per call; couples us to the CLI's argument surface and output modes; no cookie/session control from Python |
| (b) Vendor the MIT TypeScript provider modules | **Rejected** | Still ships a JS runtime; a Python package cannot call them without a bridge; porting the normalizers to Python is required either way, and the source stays canonical upstream |
| (c) Python HTTP client over `api.gloom.sh` + digifetch | **Chosen** | Cookie-less anonymous access works (verified); no Bun; full Pydantic v2 control; `digifetch` already owns transport, rate limiting, and retry; effort shifts to porting the client-side normalizers (§5.4) |
| (d) Direct-to-Yahoo/SEC/FRED in Python | **Documented fallback, not built** | Same upstream data; loses Cloud's normalization, news aggregation, and cookie-gated endpoints; would need its own Yahoo crumb handling |

Placement: `digifetch` stays the generic transport engine — no URLs, no site
logic, no env reads (its "Deliberately NOT extracted" boundary). The Gloomberb
client, endpoint constants, Pydantic models, and normalizers live in
`digiquant/src/digiquant/data/gloomberb/`. Tools register in the existing
digiquant MCP server (`mcp_server.py`), following the
`digiquant_fetch_coinbase_ohlcv` precedent — a standalone `digifetch-mcp`
server is deferred (YAGNI). Note: tools are named `digifetch_*` while deployed
inside digiquant's server; that is a deliberate naming/ownership split to keep
discovery aligned with the data-fetch family.

## 5. MCP tool surface

### 5.1 Tools

All rows use Pydantic v2 input and output models. Rows starting `| \`digifetch_`
are the test-visible contract (13 rows).

| Tool | Wraps | Endpoint | Input model | Output model | Auth |
|------|-------|----------|-------------|--------------|------|
| `digifetch_quote` | `getQuote` | `GET /market/quote` | `QuoteInput{symbol: str, exchange: str \| None}` | `QuoteResult(quote: Quote \| None)` | anon |
| `digifetch_quotes_batch` | `getQuotesBatch` | `POST /market/quotes/batch` | `QuotesBatchInput{symbols: list[str] (1–20)}` | `QuotesBatchResult(quotes: list[QuoteBatchItem])` | anon |
| `digifetch_price_history` | `getPriceHistory` | `GET /market/history` | `PriceHistoryInput{symbol, resolution: Resolution, range: Range, exchange?}` | `PriceHistoryResult(bars: list[PriceBar], metadata)` | anon |
| `digifetch_ticker_financials` | `getTickerFinancials` (+Batch) | `GET /market/financials` (+`statementHistory=extended`), `POST /market/financials/batch` | `TickerFinancialsInput{symbol, exchange?, extended_statements: bool = False}` | `TickerFinancialsResult(financials: TickerFinancials)` | anon |
| `digifetch_options_chain` | `getOptionsChain` | `GET /market/options` | `OptionsChainInput{symbol, exchange?, expiration: int \| None (epoch s)}` | `OptionsChainResult(chain: OptionsChain)` | anon |
| `digifetch_sec_filings` | `getSecFilings` / `…Documents` / `…Content` | `GET /cloud/sec/filings`, `/cloud/sec/filing/documents`, `/cloud/sec/filing/content` | `SecFilingsInput{ticker, what: Literal["filings","documents","content"], count: int = 15, cik?, accession?, form?}` | `SecFilingsResult(filings \| documents \| content)` | anon (live-verified) |
| `digifetch_holders` | `getHolders` | `GET /market/holders` | `HoldersInput{symbol, owner_type: Literal["all","insider","institution","fund","direct"] = "all"}` | `HoldersResult(holders: list[Holder])` | session cookie |
| `digifetch_analyst_research` | `getAnalystResearch` | `GET /market/analyst` | `AnalystResearchInput{symbol, limit: int = 20}` | `AnalystResearchResult(recommendation, price_target, actions: list[AnalystAction])` | session cookie |
| `digifetch_corporate_actions` | `getCorporateActions` | `GET /market/corporate-actions` | `CorporateActionsInput{symbol}` | `CorporateActionsResult(actions: list[CorporateAction])` | session cookie |
| `digifetch_earnings_calendar` | `getEarningsCalendar` | **Yahoo via `yfinance` (no Cloud route)** | `EarningsCalendarInput{symbols: list[str], horizon_days: int = 90}` | `EarningsCalendarResult(events: list[EarningsEvent])` | anon (Yahoo path) |
| `digifetch_exchange_rate` | `getExchangeRate` (+Snapshot) | `GET /market/exchange-rate` | `ExchangeRateInput{from_currency: str (ISO-4217, len 3), to_currency: str = "USD"}` | `ExchangeRateResult(rate, as_of, stale, delay_note)` | anon |
| `digifetch_search` | `search` | `GET /market/search` | `SearchInput{query, limit: int = 10 (1–10)}` | `SearchResult(results: list[InstrumentSearchResult], limit_clamped: bool)` | anon |
| `digifetch_news` | news `fetchNews` / `fetchNewsStory` | `GET /news`, `GET /news/{id}` | `NewsInput{feed: Literal["latest","top","breaking","ticker","sector","topic"] = "latest", ticker?, story_id?, limit: int = 20}` | `NewsResult(items: list[NewsItem])` | anon |

Notes:

- `digifetch_earnings_calendar` is the one non-Cloud tool: it follows
  digiquant's existing `yfinance` dependency (same upstream Yahoo exposes), and
  the Cloud client does not own it unless a Cloud route appears.
- `digifetch_holders.owner_type` exposes the upstream four owner types
  (`financials.ts:138`) plus the CLI's `insider`/`direct` and
  `institution`/`fund` variants; filtering beyond the endpoint's grouping is
  client-side.
- `digifetch_search.limit_clamped` is a result field (not only an envelope
  warning) because the server accepts a `limit` but the Cloud client wrapper
  caps at 10.
- Endpoint names/paths are the real family map: `/market/*`, `/news`,
  `/cloud/*` (§3, Validation item 6).
- `PriceBar.open/high/low/volume` are optional upstream (`financials.ts:449-457`);
  `OptionsContract.side` normalizes upstream `calls`/`puts`.

### 5.2 Resolution × range caps

The contract matches the issue's acceptance criteria, with one recorded
deviation (see below). Validation is a Pydantic v2 `model_validator` on
`PriceHistoryInput`.

| Resolution | Contract max range | Notes |
|------------|--------------------|-------|
| `1m` | 1 week | Cloud also 1W |
| `5m` | 1 week | Cloud can serve 1M — one-line widening knob |
| `15m` | 1 month | Cloud can serve 3M — one-line widening knob |
| `30m` | 6 months | Cloud-served; kept in contract |
| `1h` | 3 months | Cloud can serve 1Y |
| `1d` | 5 years (default) | matches Cloud |
| `1wk` | **5 years** — *deviation from the issue's all-time* | live probe: 29 bars for `ALL`; a direct client has no Yahoo fallback; spike item to re-measure |
| `1mo` | all-time | matches Cloud |

Range vocabulary is the `TimeRange` enum (`1D…5Y, ALL`); resolution is the
chart-resolution enum (`1m…1mo`). A request outside the contract raises
`invalid_input` (never silently clamps), matching the envelope policy in §5.3.

**Widening escape hatch (#4100).** `PriceHistoryInput` additionally accepts an
explicit `start_date`/`end_date` window (ISO `YYYY-MM-DD`, either end optional,
`start_date <= end_date`). The window is **mutually exclusive** with `range`
and bypasses the caps above: the client sends `rangeKey=ALL` + `startDate`/
`endDate`, the combination a live probe verified serves 610 weekly bars back to
2015-01-05 — beyond the `1wk` 5-year cap, while `rangeKey=ALL` alone still
returns the ~29-bar default window. The range-based caps in the table are
unchanged.

### 5.3 Envelope, errors, freshness

One shared envelope, generic over the tool payload:

```text
DigifetchEnvelope[T] {
  source: Literal["gloomberb"], provider_id: str,
  fetched_at: datetime, stale: bool, delay_note: str | None,
  warnings: list[str], data: T | DigifetchError
}
```

Each `*Result` model in §5.1 is the success-case `T`. Tools never raise to the
transport; failures return the same envelope with `data` set to a typed
`DigifetchError{code, message, retryable}` (the error-bearing type is
`DigifetchEnvelope[T | DigifetchError]`):

| Situation | code |
|-----------|------|
| Wire 401/403 (gated endpoint without cookie) | `auth_required` |
| Pro-gated route with a valid free session: 402/plan-required text or JSON body, or envelope `status: "unsupported"` + `reasonCode: "PRO_REQUIRED"` (#4110 phase 5) | `pro_required` (non-retryable, breaker-safe) |
| Wire 404 | `not_found` |
| Wire 429 (honor `Retry-After`) | `rate_limited` |
| Wire 5xx / timeout | `upstream_error` (retryable) |
| Pydantic validation failure on input | `invalid_input` |
| Envelope `status: "empty"` / `"unsupported"` (provider-miss upstream) | `not_found` |
| Envelope `status: "retryable_error"` | `upstream_error` (retryable) |
| Envelope `status: "fatal_error"` | `upstream_error` |

`pro_required` is distinct from `auth_required`: the caller has a session, it
just is not entitled (a missing/misconfigured session stays `auth_required`,
with no HTTP request on cookie-gated routes). Both Pro-gate shapes are
deterministic outcomes — never retried, never counted toward the breaker.

Wire status vocabulary (`api-client/types.ts:1036-1042`): `success | partial |
empty | unsupported | retryable_error | fatal_error`; `partial` is success with
`warnings` populated.

**Freshness.** Two distinct signals, kept distinct in the envelope:

- Wire `stale: true` means *expired cache being served*; upstream TS converts
  that to `ProviderMiss` and falls back. This client has no fallback, so it
  maps to `DigifetchEnvelope.stale = true` with
  `delay_note = "Upstream cache stale"`.
- The 15-minute free-tier delay is **not** `stale` — it is signalled by
  `dataSource: "delayed"` (`live|delayed|snapshot`) and/or `delayMinutes > 0`
  (carried by options chains and exchange-rate snapshots; quote payloads carry
  `dataSource` only). Both map to
  `delay_note = "Free-tier data delayed up to 15 minutes"`.

Freshness derivation is the union — `stale == true` OR
`dataSource == "delayed"` OR `delayMinutes > 0` — with the two notes kept
distinct. This precedence is pinned by tests.

### 5.4 Normalizers to port (fixtures required)

The TS client normalizes before display; a raw-JSON Python client must port or
consciously drop each rule, with golden fixtures (at least one GBp/LSE listing
and one intraday series):

- currency units: GBp→GBP divisor handling (`resolveCurrencyUnit`);
- interval tokens: `5m→5min`, `1d→1day`, `1wk→1week` (`normalizers.ts:253-274`);
- exchange-timezone date parsing for bar dates (ISO datetimes on the wire);
- malformed-intraday rejection for non-Yahoo upstreams;
- day-range reconciliation (quote low/high vs session data) — drop only with a
  recorded decision.

### 5.5 Transport plumbing (digifetch specifics)

`digifetch.HttpFetcher.fetch` raises on non-2xx and returns a `FetchResult`
without headers, so the client catches `httpx.HTTPStatusError` for
429/`Retry-After` extraction. `RetryPolicy.retry_on` must be narrowed to
retryable classes (not the default `(Exception,)`) so 401/404 are not retried.
The `RateLimiter` interval is a client constant (pin in implementation; the
free tier is rate-limited). Cache: a 900s TTL cache for enrichment reads
(matching the R2 market-data-cache convention) with the kill switch bypassing
it for diagnostics.

## 6. Data-source inventory and per-source digifetch path

| Source | What it provides | digifetch path | Replacement verdict |
|--------|------------------|----------------|---------------------|
| Gloom Cloud `/market/*` | quotes, history, financials, options, search, FX | `digifetch_*` tools (chosen approach (c)) | Enrichment only — 15-min delay + rate limits disqualify it as a pipeline primary |
| Gloom Cloud `/news` | aggregated wires (Reuters, CNBC, WSJ/Dow Jones, BBC, MarketWatch observed live), sentiment, sectors, importance scores | `digifetch_news` | New capability for digichat/dashboard enrichment |
| Gloom Cloud `/cloud/sec/*` | filings, documents, content | `digifetch_sec_filings` | Cross-check vs direct EDGAR |
| Yahoo (via Cloud and via `yfinance`) | quotes, history, financials | Cloud tools; Yahoo-direct only via existing `yfinance` (`data/prices/fetchers.py`) — **same underlying endpoints; no change** | Already used by digiquant |
| SEC EDGAR (direct) | filings | Fallback path (d) only | Already public |
| FRED + Treasury fiscaldata | macro | Not in this contract | Out of scope |
| Substack | newsletters | Separate Gloomberb plugin (`gloom-substack`), **not** part of the Cloud aggregator | Out of scope |
| Nasdaq/NasdaqTrader | **holiday calendars only** (Sharpe session qualification) — no symbol-file source exists in the repo | n/a | Drop from inventory |

The four user-priority feeds verdict: quotes, options, news, and financials are
all reachable anonymously today; filings are live-anon; holders/analyst/actions
need the optional session cookie. None of them replaces the pipeline's current
sources (delay, rate limits, history caps); they enrich dashboard and chat.

## 7. Attribution and external links

- Canonical attribution: **"Sourced from Gloomberb"** plus
  "data delayed up to 15 minutes" wherever a value is rendered outside the
  terminal, per the author decision.
- Deep links: `https://term.gloom.sh/?ticker=<SYMBOL>` (optionally
  `&exchange=<EX>`); published share pages are `https://term.gloom.sh/s/<id>`.
  There is no bare-path symbol route — `?ticker=` is the real form
  (`research-entry.ts`).
- No embedding: `term.gloom.sh` sends `X-Frame-Options: DENY` and
  `frame-ancestors 'none'` (§8).

## 8. Dashboard page evaluation

**Iframe embedding of `term.gloom.sh` is ruled out — it is not viable and not
recommended.** Three reasons:

1. The agent sandbox's egress proxy blocked `term.gloom.sh` at the time of the
   original investigation (observed at the time; not reproducible from a normal
   workstation — a caveat, not a load-bearing claim; the other reasons stand
   alone).
2. New external service dependency / network exposure change — trips the
   `agents.yml` human gate (§9).
3. Cross-origin iframes block digichat's popup/page-awareness from reading the
   embedded DOM, so the integration would be opaque to the agent layer.

Evaluated alternative (not committed, not built here): a same-origin digiquant
dashboard market-data page backed by the §5 data layer — quotes, history,
options snapshot, and news headlines — keeping digichat page-awareness possible
and attribution explicit. Self-hosting Gloomberb's MIT web build on Cloudflare
is parked: it is a new external service with real deployment weight.

## 9. Human gate

The chosen approach introduces **new outbound HTTP calls to
`api.gloom.sh`** (and, on the fallback path, SEC EDGAR directly). Per
`agents.yml` `human_gates` ("New external service dependency or infrastructure
change"), the follow-up implementation (issue #4069) must carry this flag and
get **explicit human sign-off before merge** — the implementation PR may not
self-merge. This scoping issue merges no dependency and no runtime call. Before
implementing, verify egress from the actual deployment runtime (digiquant MCP
container → `api.gloom.sh`) and record required headers (the TS client sends
`Origin` and `credentials: "include"`; our cookie-less path must be proven from
the container, not just the workstation). Yahoo direct remains pre-existing
(`yfinance`); the new gates are `api.gloom.sh` and optional EDGAR.

## 10. Licensing

`gloomberb` is MIT (`Copyright (c) 2026 Gloomberb Contributors`). The LICENSE
text adds an attribution-appreciation paragraph (LICENSE:15-17) — that extra
paragraph is why GitHub's license API returns `NOASSERTION`/`other` rather than
`MIT`; the code license itself is MIT. Vendoring (approach b, rejected) would
have to retain the copyright notice and MIT text in any copied file. Textual
attribution is **appreciated, not legally required**. Data Terms-of-Service for
production-scale use of `api.gloom.sh` are an open item tied to the human gate
(§9): no published ToS review has been done; volume estimates and a
User-Agent/identification policy belong to the implementation spike.

## 11. Risks

| Risk | Mitigation |
|------|------------|
| `api.gloom.sh` is undocumented and can change | Wire-validate at implementation (§12 spike); MIT source is vendorable as a last resort; typed `upstream_error` surface |
| Rate limits / 15-min delay on free tier | 900s TTL cache; `RateLimiter`; honor `Retry-After`; enrichment-only positioning |
| Upstream breakage degrades the agent layer | Tools default ON per author decision, but a kill-switch flag disables the family instantly; a circuit breaker (N consecutive failures → typed error) prevents retry storms; "api.gloom.sh unavailable → enrichment degraded, pipeline unaffected" is the documented behavior |
| Normalizer porting introduces silent unit/interval bugs | §5.4 fixtures (GBp, intraday) as tests before registration |
| Session cookie used for gated tools leaks | Cookie supplied via env secret (`GLOOMBERB_SESSION_COOKIE`), never logged, never in tool input; clear error `auth_required` when absent |
| `digifetch` interface changes (provisional, 0.1.0, one consumer) | Any needed engine change lands with its own review in `digifetch/`; digiquant adds the dep explicitly (§12) |
| Unvalidated CI (bun) and truncated history | Open spike items (§12): run `bunx gloomberb api list --json` diff; re-measure the 1wk truncation |
| ToS/legal at production scale | Open item under the human gate (§9/§10) |

## 12. Follow-up implementation outline (issue #4069)

1. Declare `digifetch` (and `httpx`, `yfinance`) in `digiquant/pyproject.toml`
   (the dev workspace already provides them, so CI alone will not catch the
   omission).
2. Build `digiquant/src/digiquant/data/gloomberb/`: endpoint constants, Pydantic
   v2 models (§5.1), `DigifetchEnvelope[T]`, normalizers (§5.4) with fixtures,
   freshness union (§5.3), transport via `digifetch` (§5.5).
3. Register the 13 tools in `mcp_server.py` via the `_maybe_tool` pattern and
   add the orchestrator manifest entries (`orchestrator_tools.py`), scope
   `read`; decide family exposure behind the kill switch.
4. Tests: golden fixtures (GBp + intraday), envelope/error mapping, freshness
   precedence, caps validator; live smoke behind an opt-in marker.
5. Spike (before freezing models): run `bunx gloomberb api list --json` diff on
   a Bun machine and amend §3; re-measure the 1wk/`ALL` truncation; verify
   container egress to `api.gloom.sh` incl. `Origin`/User-Agent; ToS/volume
   check.
6. Rollout: tools default ON (author decision) with kill switch, 900s TTL
   cache, circuit breaker; document the degraded-mode behavior; update
   `digiquant/AGENTS.md` (not touched by this scoping task).
7. Attribution wiring: tearsheet/stock-page deep links
   (`?ticker=`), "Sourced from Gloomberb" strings, delay notice.

## 13. References

- Scoping issue: [#3927](https://github.com/digithings-ai/digithings/issues/3927)
- Implementation follow-up: [#4069](https://github.com/digithings-ai/digithings/issues/4069)
- Prior art: [2026-09-09-r2-market-data-cache-design.md](2026-09-09-r2-market-data-cache-design.md)
  (live-fetch precedent in the digiquant MCP server —
  `digiquant_fetch_coinbase_ohlcv`, `digiquant.data.prices.history_cache`; 900s
  TTL convention reused here)
- Upstream: `gloom-sh/gloomberb` (MIT), `src/types/data-provider.ts`,
  `src/sources/gloomberb-cloud/index.ts`, `src/api-client/paths.ts`
- digifetch boundary: [digifetch/ARCHITECTURE.md](../../../digifetch/ARCHITECTURE.md)
