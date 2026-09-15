# digifetch × Gloomberb — AssetDataProvider MCP Scoping — Design Spec

> **For agentic workers:** This is a DESIGN SPEC, not an implementation plan.
> Do not implement from this file. The implementation plan (writing-plans skill)
> is written only after the user approves this spec.

**Date:** 2026-09-12 (issue) · 2026-09-15 (source validation)
**Status:** draft — awaiting user review
**Issue:** [#3927](https://github.com/digithings-ai/digithings/issues/3927) — `[agent] Scope digifetch: MCP wrapper for Gloomberb's AssetDataProvider + dashboard-page evaluation`
**Validated against:** `gloom-sh/gloomberb` v0.13.3 (`package.json`), shallow clone
of `main` @ 2026-09-15. File/line cites below are from that revision.

**Author decision (verbatim, from the live review session):** use Gloomberb as an
**external-link integration** first — link digiquant tearsheets / stock pages to
Gloomberb pages for a third-party-integration feel — and fetch a few things
(headlines, quotes) via the digifetch path, clearly attributed as "sourced from
Gloomberb". If quotes, options, news, and financials can all come from this one
free source with history, evaluate replacing the current pipeline sources.
This spec answers both halves: the MCP tool surface for the digifetch path, and
a source-by-source verdict on replacement.

---

## 1. Goal

Produce a scoping/design spec (no implementation code) for consuming
Gloomberb's `AssetDataProvider` surface as a `digifetch` MCP tool family for
Python agents and digichat, plus an evaluation of a same-origin digiquant
dashboard market-data page instead of iframing `term.gloom.sh`.

In scope:

- Field-for-field validation of the capability surface against the real
  Gloomberb source and its capability JSON.
- A clear recommendation among the candidate integration approaches.
- The 12 `digifetch_*` MCP tools with Pydantic v2 input/output models and
  resolution × range validation.
- A data-source inventory with the digifetch path for each source.
- External-link + attribution design (the "third-party integration feel").
- Dashboard-page evaluation (same-origin page; iframe ruled out).
- Human-gate and licensing statements for the follow-up implementation.

Out of scope (explicitly not done here): any implementation code, any change to
digiquant pipeline data sources, vendoring Gloomberb modules, self-hosting the
Gloomberb web build, and `digiquant/AGENTS.md` updates (those come with the
implementation issue).

---

## 2. Background — Gloomberb at a glance

| Fact | Value |
|------|-------|
| Project | `gloom-sh/gloomberb` — "Finance terminal, in your terminal." |
| License | MIT (`LICENSE`: "MIT License, Copyright (c) 2026 Gloomberb Contributors") — GitHub API reports `NOASSERTION` because the file header is plain MIT without an SPDX tag |
| Version / stack | 0.13.3 · TypeScript + Bun (`packageManager: bun@1.3.11`; CLI shebang `#!/usr/bin/env bun`) |
| Surfaces | TUI (default), desktop (Electrobun), browser app `term.gloom.sh`, and a JSON-capable CLI — all share one data layer and plugin system |
| Data layer | Plugin/provider stack: **Gloom Cloud** (`api.gloom.sh`, priority 100, featured primary) → **Yahoo** fallback (always-on, non-toggleable) → supplemental sources (SEC EDGAR, FRED, Treasury, news wires, NasdaqTrader) |
| Auth model | Anonymous cookie-less HTTP works for quotes, history, financials, options, news, search, FX. Signup + email verification gates SEC filings, holders, analyst research, corporate actions |
| Free tier | Rate-limited and **15-minute delayed** (`README.md` line 30, `docs/browser.md`); Pro = realtime |
| Hosted terminal framing | `x-frame-options: DENY` + CSP `frame-ancestors 'none'` (verified live on `term.gloom.sh`, 2026-09-15) |

The upstream data behind Gloom Cloud is largely the **same Yahoo Finance**
endpoints digiquant already uses directly (`query1.finance.yahoo.com`,
`query2.finance.yahoo.com`), plus SEC/FRED/Treasury for the public sources.
Gloomberb's value-add is aggregation, normalization, ranking/importance
metadata on news, and a uniform provider contract — not a unique data feed.

---

## 3. Capability validation against real source

`AssetDataProvider` (`src/types/data-provider.ts`, 219 lines) is the contract
consumed by the plugin router. The provider implementation of interest is
`GloomberbCloudProvider` (`src/sources/gloomberb-cloud/index.ts`, 625 lines),
id `gloomberb-cloud`, name "Gloom Cloud", priority 100.

| Provider method | Cloud-gated? | Verified in source | digifetch tool |
|-----------------|--------------|--------------------|----------------|
| `getQuote` | no | index.ts (`withCloudFallback` path) | `digifetch_quote` |
| `getQuotesBatch` | no | index.ts | `digifetch_quotes_batch` |
| `getPriceHistory` / `getPriceHistoryForResolution` / `getDetailedPriceHistory` | no | index.ts; caps `CLOUD_RESOLUTION_SUPPORT` lines 60–69 | `digifetch_price_history` |
| `getTickerFinancials` / `getTickerFinancialsBatch` | no | index.ts; fields in `src/types/financials.ts` lines 475–478 (`fundamentals`, `profile`, `annualStatements`, `quarterlyStatements`) | `digifetch_ticker_financials` |
| `getOptionsChain` | **no** | index.ts (`getCloudOptionsChain`) | `digifetch_options_chain` |
| `getSecFilings` | **yes** — `requireVerifiedSession()` | index.ts; `SecFilingItem` preserves raw `acceptanceDateTime` (`acceptedAtRaw`) | `digifetch_sec_filings` |
| `getSecFilingDocuments` | **yes** | index.ts | `digifetch_sec_filings` (`what="documents"`) |
| `getSecFilingContent` | **yes** | index.ts | `digifetch_sec_filings` (`what="content"`) |
| `getHolders` | **yes** | index.ts | `digifetch_holders` |
| `getAnalystResearch` | **yes** | index.ts | `digifetch_analyst_research` |
| `getCorporateActions` | **yes** | index.ts | `digifetch_corporate_actions` |
| `getEarningsCalendar` | n/a — not implemented on Cloud | Yahoo provider (`src/sources/yahoo-finance.ts`), routed by `provider-router/supplemental.ts` | `digifetch_earnings_calendar` (Yahoo-backed) |
| `getExchangeRate` / `getExchangeRateSnapshot` | no | index.ts | `digifetch_exchange_rate` |
| `search` | no (results capped at 10, `apiClient.searchInstruments(query, 10)`) | index.ts | `digifetch_search` |

Methods deliberately **not exposed** as tools: `getCachedQuery` /
`getCachedFinancialsForTargets` (cache handles, not agent-facing),
`subscribeQuotes` (streaming), `getQuoteMetadata` (listing facts folded into
`digifetch_quote` output), `getArticleSummary` (throws `ProviderMiss` on Cloud —
lazy on-selection only).

### Validation

Source-verified in the local clone (2026-09-15): provider contract, auth gating,
resolution caps, CLI record shapes (`src/cli/commands/market.ts`, 484 lines),
and request semantics (`src/api-client/request.ts`: cookie-session auth,
10 s `/market/` timeout, `Retry-After` parsing).

Discrepancies vs the paraphrased summary in #3927 that the spec corrects:

1. **Caps differ from the issue's list.** The Cloud provider can serve more
   than the conservative caps named in the acceptance criteria
   (`CLOUD_RESOLUTION_SUPPORT`, lines 60–69): 1m→1W, 5m→1M, 15m→3M, 30m→6M,
   1h→1Y, 1d→5Y, 1wk→5Y, 1mo→ALL. The base library default
   (`src/time-series/resolution.ts` lines 162–167) is 5m→1W, 15m→1M, 1h→3M,
   1d→5Y, 1wk→ALL, 1mo→ALL. **This spec adopts the issue's conservative caps as
   the initial tool contract** (§5.2) and records the wider Cloud caps as a
   follow-up widening knob — widening needs no client change.
2. **No credentials is only true for the ungated subset.** SEC filings,
   holders, analyst research, and corporate actions require a signed-up,
   email-verified Cloud session. Options chains are *not* gated (good news for
   the "replace current sources" question). The earnings calendar is not a
   Cloud capability at all — it is served by the Yahoo fallback provider, so
   its tool is out of scope for the Cloud HTTP client until a Cloud route
   exists (see §3 table, §5.1, §6).
3. **Twelve tools, not fourteen.** The issue lists 14 method names but its own
   count test expects 12 rows; the SEC filings family (filings → documents →
   content) is one tool with a `what` discriminator.
4. **Not a unique data source.** Cloud's upstream is Yahoo (same source as
   digiquant's current fetchers) plus SEC/FRED/Treasury. Aggregation and news
   prioritization are the differentiators, not wholesale replacement of feeds.
5. **CLI JSON cannot be validated in CI or locally.** `bun` is not installed
   in the agent environment; `bunx gloomberb api list --json` requires a Bun
   runtime. The follow-up implementation must run
   `bunx gloomberb api list --json > /tmp/gloomberb-capabilities.json` once on
   a machine with Bun and diff the capability keys against §5's tool table;
   `src/cli/commands/market.ts` record shapes in §5 are the source-verified
   stand-in.

---

## Decision

**Recommended approach: (c) — a Python HTTP client against the same JSON
endpoints the Gloomberb CLI uses (`api.gloom.sh`), with `digifetch` providing
transport (httpx fetch, rate limiting, retry) and the Gloomberb-specific URLs,
models, and parsing living in the digiquant consumer.** Neither issue candidate
is chosen: (a) CLI shell-out and (b) TS vendoring are both rejected below.
"Chosen approach" is (c) with (d) as the documented fallback.

| # | Approach | Verdict | Why |
|---|----------|---------|-----|
| (a) | CLI shell-out (`bunx gloomberb … --json`) | **Rejected** | Adds a Bun runtime + subprocess to a Python service; couples tool contracts to a CLI arg surface that can change without semver notice; per-call process spawn costs ~100–300 ms before any network; no reuse from the dashboard (a browser cannot spawn the CLI). Recommended only as a debugging/diff harness. |
| (b) | Vendor the MIT TS provider modules | **Rejected** | Still ships a JS runtime (Bun or Node) for Python to consume, so the runtime dependency problem is unchanged; vendored code forks immediately (upstream moves fast — pushed the day of validation); parsing/HTTP logic is small enough that a Python client is the smaller maintenance burden. |
| (c) | **Python HTTP client against `api.gloom.sh`** | **Chosen** | No Bun, no subprocess; full Pydantic v2 control over inputs/outputs; identical data because it is the same API the CLI calls (cookie-less anonymous where allowed, session cookie where gated); reuses `digifetch.HttpFetcher` / `RateLimiter` / `with_retry`; the dashboard and digichat share the same client; the API client contract is pinned by §3's source validation. |
| (d) | Direct-to-source (Yahoo/SEC/FRED) with no Gloomberb | Documented fallback | Zero third-party contract risk, but re-implements the aggregation/normalization Gloomberb already did — and Cloud's Yahoo upstream is the same data. Use as fallback if `api.gloom.sh` access breaks; keep the tool schemas identical so consumers do not change. |

Trade-offs compared as the acceptance criteria require: **(a)** lowest initial
code, highest runtime and coupling cost; **(b)** low transport code, but a
permanent fork and still a JS runtime; **(c)** moderate initial client code,
lowest runtime cost, best dashboard-reuse potential (the dashboard's future
market-data page and digichat consume the same Python client), and testable
without a network (mocked `httpx.MockTransport`, the existing digifetch test
seam). Subprocess overhead: (a) high per call (spawn), (c) none.

Placement (respects both components' rules):

- `digifetch` stays the generic transport engine — no URLs, no site logic, no
  env reads (its `ARCHITECTURE.md` "Deliberately NOT extracted" boundary).
- The Gloomberb client lives in the consumer: a new
  `digiquant/src/digiquant/data/gloomberb/` package (client + Pydantic models +
  normalizers) — the consumer owns URLs, parsing, and models, following
  digifetch's "Deliberately NOT extracted" boundary (as with twelve-x).
- The 12 tools register in the **existing digiquant MCP server**
  (`digiquant/src/digiquant/mcp_server.py`, FastMCP streamable-http, default
  `127.0.0.1:8767`), following the `digiquant_fetch_coinbase_ohlcv` pattern.
  A standalone `digifetch-mcp` server is deferred (YAGNI): it would add a new
  port/service surface for no consumer that the digiquant server does not
  already serve.

---

## 5. MCP tool surface

All tools live under the `digifetch_` namespace (fixed by #3927), are read-only,
and return a single JSON envelope (never raise to the transport — the existing
MCP server pattern wraps errors as `{"error": …}`).

### 5.1 The twelve tools

| Tool | Wraps | Input model (Pydantic v2) | Output model | Auth | Notes |
|------|-------|---------------------------|--------------|------|-------|
| `digifetch_quote` | `getQuote` | `QuoteInput{symbol: str, exchange: str \| None}` | `QuoteResult{target, quote: Quote \| None, error: DigifetchError \| None}` | anon | Single-symbol; `Quote` carries price, change, currency, provider, `updated_at`, `stale` |
| `digifetch_quotes_batch` | `getQuotesBatch` | `QuotesBatchInput{symbols: list[str] (1–20), exchange: str \| None}` | `QuotesBatchResult{quotes: list[QuoteResult], partial: bool}` | anon | Per-target error isolation, never all-or-nothing |
| `digifetch_price_history` | `getPriceHistory` | `PriceHistoryInput{symbol, exchange?, resolution, range}` | `PriceHistoryResult{symbol, resolution, range, points: list[PricePoint], source}` | anon | Resolution × range validated against §5.2 caps; `PricePoint{date, open, high, low, close, volume}` (`open/high/low/volume` optional upstream) |
| `digifetch_ticker_financials` | `getTickerFinancials` | `TickerFinancialsInput{symbol, exchange?, statement_history?: "annual"\|"quarterly"\|"both"}` | `TickerFinancialsResult{fundamentals: Fundamentals \| None, profile: CompanyProfile \| None, annual_statements: list[FinancialStatement], quarterly_statements: list[FinancialStatement]}` | anon | Mirrors `src/types/financials.ts` lines 475–478 |
| `digifetch_options_chain` | `getOptionsChain` | `OptionsChainInput{symbol, exchange?, expiration?: date}` | `OptionsChainResult{expiration_dates: list[date], contracts: list[OptionsContract]}` | anon | `OptionsContract{side, contract_symbol, strike, last, bid, ask, volume, open_interest, implied_volatility, expiration}` (`side` normalizes upstream `calls`/`puts`) |
| `digifetch_sec_filings` | `getSecFilings` + `getSecFilingDocuments` + `getSecFilingContent` | `SecFilingsInput{symbol, exchange?, count: int = 15 (1–40), what: "filings"\|"documents"\|"content" = "filings", accession_number: str \| None}` | `SecFilingsResult{filings: list[SecFilingItem] \| None, documents: list[SecFilingDocument] \| None, content: SecFilingContent \| None}` | **session** | One tool for the filings family (`what` discriminator); `documents`/`content` require `accession_number`; preserves `accepted_at_raw` (SEC acceptance timestamp, no TZ inference) |
| `digifetch_holders` | `getHolders` | `HoldersInput{symbol, owner_type: "all"\|"insider"\|"institution" = "all"}` | `HoldersResult{holders: list[Holder], summary: HoldersSummary \| None}` | **session** | `owner_type` replaces the CLI's `insider`/`13f` variants |
| `digifetch_analyst_research` | `getAnalystResearch` | `AnalystResearchInput{symbol, limit: int = 20}` | `AnalystResearchResult{ratings: list[AnalystRating], recommendation: RecommendationSummary \| None}` | **session** | `AnalystRating{date, firm, action, current, prior, price_target}` |
| `digifetch_corporate_actions` | `getCorporateActions` | `CorporateActionsInput{symbol, kinds?: list["earnings"\|"dividend"\|"split"]}` | `CorporateActionsResult{actions: list[CorporateAction]}` | **session** | `CorporateAction{kind, date, detail}` |
| `digifetch_earnings_calendar` | Yahoo provider (not Cloud) | `EarningsCalendarInput{symbols: list[str], horizon_days: int = 90}` | `EarningsCalendarResult{events: list[EarningsEvent]}` | anon (Yahoo path) | `EarningsEvent{symbol, name, date, timing, eps_estimate, eps_actual, revenue_estimate, revenue_actual}`; no Cloud endpoint exists (§5.1 exception) |
| `digifetch_exchange_rate` | `getExchangeRate` / `getExchangeRateSnapshot` | `ExchangeRateInput{from_currency: str, to_currency: str = "USD"}` | `ExchangeRateResult{from_currency, to_currency, rate, as_of}` | anon | Snapshot variant drives `as_of` |
| `digifetch_search` | `search` | `SearchInput{query: str, limit: int = 10 (1–10)}` | `SearchResult{results: list[InstrumentSearchResult]}` | anon | Provider caps results at 10 — a caller asking for more gets a `limit_clamped` warning field, not more rows |

Names, counts, and the tool-per-method mapping above satisfy the #3927 count
test (12 rows) while covering all 14 provider method names via the filings
family and the batch/history variants.

Exception: `digifetch_earnings_calendar` wraps `getEarningsCalendar`, which has
**no Cloud endpoint** — it is served by the Yahoo fallback provider
(`yahoo-finance.ts` via `provider-router/supplemental.ts`). It is specified here
for completeness of the method census, but the Cloud HTTP client does not own
it until a Cloud route exists.

### 5.2 Resolution × range caps

Validation is enforced in the Pydantic input model (a `model_validator` raising
on unsupported pairs) so an invalid request never leaves the process:

| Resolution | Max range (contract) | Cloud-served max (source) | Notes |
|------------|----------------------|---------------------------|-------|
| `1m` | not offered | 1W | Keep unoffered until a consumer needs it |
| `5m` | 1W | 1M | |
| `15m` | 1M | 3M | |
| `30m` | not offered | 6M | Keep unoffered until a consumer needs it |
| `1h` | 3M | 1Y | |
| `1d` | 5Y (default range `1Y` per request) | 5Y | Default resolution |
| `1wk` | all-time | 5Y (Cloud) — all-time falls back to Yahoo | |
| `1mo` | all-time | ALL | |

The contract matches the acceptance criteria exactly; §3 (Validation item 1)
records the full Cloud table. `1wk` is the one row where the contract is *wider*
than Cloud (all-time vs 5Y) — that range relies on the Yahoo fallback. Every
other widening is a one-line table edit.

### 5.3 Shared envelope, errors, and freshness

Every tool returns `DigifetchEnvelope{source="gloomberb", provider_id,
fetched_at, stale: bool, delay_note: str | None, data, warnings: list[str]}`.
`stale=true` and `delay_note="free tier: data delayed up to 15 minutes"` are set
when the response indicates stale/partial provider metadata. Errors are typed:
`DigifetchError{code: "auth_required" | "rate_limited" | "provider_miss" |
"network" | "invalid_input" | "upstream_error", message, retry_after_ms: int |
None}` — `rate_limited` maps from HTTP 429 + `Retry-After`; `auth_required`
maps from the `requireVerifiedSession()` failure path. No tool treats a
`provider_miss` (symbol not found / unsupported data) as a hard error.

---

## 6. Data-source inventory and digifetch path per source

Exploration round requested in the live session: exactly which sources exist
and what the digifetch path is for each. From the outbound-host census and
`src/sources/` layout:

| Source | Endpoint(s) | Free / auth | digifetch path | Replacement verdict for pipeline |
|--------|-------------|-------------|----------------|----------------------------------|
| Gloom Cloud (primary) | `api.gloom.sh/cloud/*` | free tier rate-limited, 15-min delayed; signup for gated methods | Chosen path (c) — direct Python client | **Enrichment only** — delay + rate limits disqualify realtime/live |
| Yahoo Finance (fallback) | `query1/query2.finance.yahoo.com`, `finance.yahoo.com` | free, unofficial, delayed | Already used by digiquant via the `yfinance` library (`data/prices/fetchers.py`) — same underlying endpoints; no change | Same upstream as Cloud; keep direct fetchers |
| SEC EDGAR | `www.sec.gov`, `data.sec.gov` | free, public | Cloud client (session) or direct EDGAR later via (d) | Enrichment (filings text, holders) |
| FRED / Treasury | `fred.stlouisfed.org`, `api.fiscaldata.treasury.gov` | free, public | Direct (no Cloud dependency worth it) | Existing digiquant macro ingest already covers this |
| News wires | Dow Jones/WSJ feeds, BBC, CNBC search, HN, Substack via Cloud aggregator | free via Cloud | **Deferred** — not in this spec's 12-tool contract; the Cloud news provider is ungated, so a `digifetch_news` tool is a small follow-up addition (§12 item 7) | **Strongest pull** — aggregated headlines + topic/tickers/importance metadata is new capability |
| NasdaqTrader symbol files | `www.nasdaqtrader.com` | free, public | Deferred (supplemental listing data) | Not needed now |
| Issuer IR pages (ICE, SSGA), 13F aggregators | various | free | Deferred | Not needed now |

Bottom line: Gloomberb **does not replace** the pipeline's price/history
sources (15-minute delay, rate limits, 5Y daily-history cap vs digiquant's
needs), but it **does add** news/sentiment headlines, fundamentals cross-checks,
options snapshots, and dashboard enrichment from one contract.

---

## 7. Attribution and external-link integration

The external-link half of the author decision, with no data dependency:

- Digiquant tearsheet / stock pages deep-link out to the matching Gloomberb
  page (`term.gloom.sh/<symbol>`; public share pages need no account,
  `docs/browser.md`). Link out with `target="_blank" rel="noopener"`; no
  embedding (see §8).
- Any data rendered from the digifetch path carries visible attribution:
  **"Sourced from Gloomberb"** (plus "data delayed up to 15 minutes" when
  `stale=true`). This is honest even before Pro credentials exist.
- Tool envelopes carry the same attribution string so agent answers and
  digichat citations are consistent.
- MIT attribution (see §10) applies to any vendored code — none is planned
  under the chosen approach, but the notice text is recorded here so a future
  re-decision does not have to re-derive it.

---

## 8. Dashboard page evaluation

**Iframe embedding of `term.gloom.sh` is ruled out — it is not viable and not
recommended.** Three named reasons, verified live (2026-09-15):

1. **Sandbox egress proxy blocked it.** The agent/desktop sandbox egress proxy
   already refused the hosted terminal in practice, and no configuration
   change makes a cross-origin frame load where egress is denied.
2. **`agents.yml` human-gate.** Embedding a third-party hosted surface is a
   "new external service dependency or network exposure change" — it trips the
   human gate and would need explicit sign-off for something the page itself
   may later remove (headers or hosting).
3. **Cross-origin iframes block digichat page-awareness.** digichat's
   page-awareness cannot read the embedded DOM of a cross-origin frame
   (`term.gloom.sh` sends `frame-ancestors 'none'` + `X-Frame-Options: DENY`,
   so the frame would not even render; and even if it did, the same-origin
   policy blocks reading it). This defeats the originating idea of digichat
   answering questions about what the user sees.

**Evaluated alternative (not committed, not built here):** a same-origin
digiquant dashboard market-data page backed by the §5 digifetch data layer —
quotes, a compact chart, news headlines, fundamentals summary — rendered in
digiquant's own DOM. This keeps digichat page-awareness possible (same-origin
DOM the page-awareness layer can read), needs no new hosting, and reuses the
same client as the MCP tools. The self-hosting route (Gloomberb ships
`wrangler.jsonc` / `wrangler.production.jsonc` for its own Cloudflare web
build) is parked: it is the only way to embed their UI, it is a new external
service, and the same-origin page is the cheaper 80%.

---

## 9. Human gate

The follow-up **implementation** issue must carry the `new external service
dependency` flag per `agents.yml` `human_gates`: the 12 tools introduce new
outbound HTTP calls to `api.gloom.sh` (and, on the (d) fallback path, to Yahoo
Finance and SEC EDGAR — public, credential-free, but still new outbound
dependencies). That requires **explicit human sign-off before merge**; the
implementation PR may not self-merge.

This scoping issue does **not** merge any dependency: it changes two
documentation files only, touches no runtime path, and no data flow changes
until a follow-up is approved. The human gate applies at implementation, not
at this spec.

---

## 10. Licensing

- Gloomberb is **MIT** ("Copyright (c) 2026 Gloomberb Contributors"). The
  chosen approach (c) talks to their API over HTTP and ships no Gloomberb
  code, so no notice obligation attaches today.
- If a future decision re-opens vendoring approach (b), any vendored file must
  retain the gloom-sh/gloomberb **copyright notice** and the MIT text in the
  vendored source; the upstream README also asks for **textual attribution** —
  appreciated, not legally required.
- Data-level terms differ from code licensing: `api.gloom.sh` is an
  unofficial, rate-limited free tier; the client must respect `Retry-After`
  and must not be used for realtime or redistribution claims.

---

## 11. Risks and open questions

| Risk / question | Mitigation |
|-----------------|------------|
| `api.gloom.sh` is undocumented and can change without notice | Contract pinned by §3 validation; typed `provider_miss`/`upstream_error`; (d) fallback keeps tool schemas stable |
| Free-tier 15-minute delay misread as live data | `stale`/`delay_note` in every envelope + visible attribution; never used in pipeline execution paths |
| Rate limits under digichat fan-out | Client-side `RateLimiter` + `Retry-After` backoff; batch tools preferred over per-symbol loops |
| Gated methods need a Cloud account | Tools return `auth_required`; ungated 8 tools ship first; session cookie storage is a follow-up decision (must not put credentials in digiquant's Postgres without a review) |
| Bun not installed — `api list --json` diff unrun | Recorded as the one open AC-1 step; run on a Bun machine during implementation |
| `src/types/financials.ts` field-level diff beyond the four top-level keys | Top-level confirmed (lines 475–478); statement row fields are mapped from CLI shapes (`market.ts`) — implementation issue re-checks against `financials.ts` before freezing models |

---

## 12. Follow-up implementation outline (not this task)

1. `digiquant/src/digiquant/data/gloomberb/` — client + Pydantic models + envelope,
   built on `digifetch.HttpFetcher` / `RateLimiter` / `with_retry`;
   `httpx.MockTransport` tests (CI never hits the network).
2. Register the 12 tools in `digiquant/src/digiquant/mcp_server.py`
   (`_maybe_tool`-style wrapper, JSON envelopes, error isolation).
3. External links + "Sourced from Gloomberb" on the digiquant stock/tearsheet
   pages; no embedding.
4. Dashboard same-origin market-data page (evaluated in §8) — separate issue
   if wanted.
5. Run `bunx gloomberb api list --json` on a Bun machine; diff against §5 and
   amend this spec's Validation section.
6. Human sign-off for the new outbound dependency before merge (§9).
7. **News** — add `digifetch_news` (the Cloud news provider is ungated); deferred from the 12-tool contract above.

---

## 13. References

- Issue: [#3927](https://github.com/digithings-ai/digithings/issues/3927)
- Prior art: [`2026-09-09-r2-market-data-cache-design.md`](2026-09-09-r2-market-data-cache-design.md)
  — live-fetch MCP precedent (`digiquant_fetch_coinbase_ohlcv`,
  `digiquant.data.prices.history_cache`) and the single-read-path MCP pattern
  this spec follows.
- Upstream: [gloom-sh/gloomberb](https://github.com/gloom-sh/gloomberb) —
  `src/types/data-provider.ts`, `src/types/financials.ts`,
  `src/sources/gloomberb-cloud/index.ts`, `src/cli/commands/market.ts`,
  `src/api-client/request.ts`, `src/time-series/resolution.ts`, `docs/usage.md`,
  `docs/browser.md`.
