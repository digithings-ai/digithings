# digifetch coverage expansion — Design Spec

> **For agentic workers:** this is a design spec, not an implementation plan. It
> ships no code. The executable plan for the first remaining phase is
> `docs/superpowers/plans/2026-09-16-digifetch-coverage-expansion.md`; later
> phases get their own plans at pickup (§7).

- **Date:** 2026-09-16
- **Status:** draft — for owner review. **The issue text of #4110 is stale:** the
  "ready to add" matrix already shipped (§2.1). This spec records the shipped
  contract of record and narrows the remaining work to the residual endpoints
  plus the deferred plugin-pane classes.
- **Issue:** [#4110](https://github.com/digithings-ai/digithings/issues/4110)
  (`component:digiquant`, priority:medium)
- **Verified against:** worktree checkout of `origin/develop` at
  `118966117` (2026-09-16). Every file:line below was read in that tree.
- **Builds on:** [2026-09-12-digifetch-scoping-design.md](2026-09-12-digifetch-scoping-design.md)
  (#3927; approach (c)), which this expansion must not re-litigate.

---

## 1. Goal and scope

**Goal.** Complete #4110's objective — full read coverage of the Gloomberb
platform surface as MCP-first `digifetch_*` tools — by (a) recording the
contract of the 33 shipped tools, (b) specifying the two residual endpoints
precisely, and (c) disposing of the plugin-only panes with recorded decisions
instead of leaving them ambiguous.

**In scope**

- A normative coverage matrix (§6) for every tool, shipped and residual.
- Precise contracts (§4) for the residual tools:
  `digifetch_transcripts` detail mode (`/cloud/transcripts/{id}`) and the new
  `digifetch_saved_searches` (`/cloud/search/saved`).
- NFRs as exact numbers read from the current code (§5).
- Phase sequencing with explicit scope cuts (§7) and the plan split.
- Measurable verification (§8).

**Out of scope**

- Implementation in this task (this spec and its plan only).
- Re-specifying the 33 shipped tools: their contracts are already pinned by
  code, ARCHITECTURE §5, and the test suite; §6 is a map to them, not a redesign.
- Surface integration (deep links / attribution in digiquant pages and
  digichat) — [#4098](https://github.com/digithings-ai/digithings/issues/4098).
- Any new external dependency beyond the already-shipped `api.gloom.sh`
  (§2.3). Non-gloomberb sources need a new issue + human gate.

---

## 2. Background (verified 2026-09-16, `origin/develop@118966117`)

### 2.1 The issue's coverage matrix already shipped

#4110's "ready to add" table is implemented on `develop`; the issue body has
not been updated since. Mapping:

| #4110 phase (issue) | Contents | Shipped in |
|---|---|---|
| 1 — macro/econ + transcripts + congress + research search | `digifetch_econ_calendar`, `digifetch_econ_series`, `digifetch_yield_curve`, `digifetch_cds`, `digifetch_research_search`, `digifetch_congress_trades`, `digifetch_transcripts` | PR #4112 (commit `3e2cc1032`), review fixes `6172c0486`; merge `6e5459aaa` |
| 2 — social + market extras + 13F | `digifetch_statements`, `digifetch_ticker_tweets`, `digifetch_tweet_search`, `digifetch_venues`, `digifetch_screener`, `digifetch_13f_funds`, `digifetch_13f_holdings` | PR #4119 (commit `a37cb3189`), review fixes `5348db7a2`; merge `a15eb1f0a` |
| 3 — plugin-only panes (the subset with a real endpoint) | `digifetch_shiller`, `digifetch_proxy_statements`, `digifetch_risk_reports`, `digifetch_filing_events`, `digifetch_short_interest`, `digifetch_equity_diagnostic` | PR #4126 (commit `20dfa71af`), review fixes `51fa8afdc`; merge `e109891a4` |
| 5 — entitlements (`free`/`session`/`preview`/`pro`) | `data/gloomberb/entitlements.py`, MCP + manifest surfacing | PR #4135 (commit `f98b88aa0`), review fixes `eeb5502c8`; merge `5d8bb6dbc` |
| 4 — digiquant surface integration | — | open, owned by #4098 |

The 33-tool family is registered in
`digiquant/src/digiquant/mcp_server.py:501-533` (`READ_SCOPE_TOOLS`) with
wrappers at `:896-1534`, declared in
`digiquant/src/digiquant/data/gloomberb/entitlements.py:58-96`
(`TOOL_ENTITLEMENTS`), listed in
`digiquant/src/digiquant/orchestrator_tools.py:1515-1577`, and routed
in-process by `digiquant/src/digiquant/data/gloomberb/agent_tools.py:310-356`
(`DIGIFETCH_DISPATCH`).

### 2.2 What actually remains of #4110

Two endpoints from the issue's "ready to add" table are not yet tool-exposed:

| Endpoint | Status | Evidence |
|---|---|---|
| `GET /cloud/transcripts/{id}` | **Residual** — the list route shipped; the detail route is explicitly recorded as a candidate extension | `digiquant/ARCHITECTURE.md:1344-1346`; `digiquant/AGENTS.md:617-619` |
| `GET /cloud/search/saved` | **Residual** — no occurrence anywhere in the tree | `grep -rn "search/saved" digiquant/` → no match (2026-09-16) |

Everything else in the issue's matrix is reachable through a shipped tool
(§6): the 13F family's seven routes are covered by the two `what`-discriminated
tools (`client.py:1634-1705`), and phase 3 overshot the issue's list by
shipping the `shiller` / `proxy_statements` / `filing_events` /
`risk_reports` / `short_interest` / `equity_diagnostic` endpoints as well.

The remaining "plugin-only panes" split into three classes (§7, decisions D5):

1. **Already shipped endpoints** — valuation (`shiller`, `equity_diagnostic`),
   executives (`proxy_statements`, `filing_events`) — done in #4126.
2. **Client-side composition over shipped tools** — correlation/relationship
   graph, world indices / FX / futures, volatility / credit conditions,
   dividend yield. These need no new fetch; they are UI/agent composition.
3. **Non-gloomberb third-party sources** — treasury auctions
   (`api.fiscaldata.treasury.gov`), prediction markets (local model,
   kelly-sizer), the live scanner (websocket stream). These are **not**
   extensions of the shipped dependency and must not be added under #4110.

### 2.3 Human-gate status (the one true gate)

The base external dependency **`api.gloom.sh` already exists and shipped**
(PR #4085, issue #4069 closed COMPLETED). Extending the read-only tool family
inside that dependency is therefore **not a new external service dependency or
network exposure change** under `AGENTS.md` § Human gate, and does not re-open
the gate. The gate that *does* apply to every remaining phase: **do not add
any non-gloomberb external dependency** (treasury auctions / fiscaldata is the
live example). If a pane cannot be served from `api.gloom.sh` plus shipped
digiquant capabilities, the correct move is a new issue carrying the
`agents.yml` human gate — not a quiet fetch in this family.

### 2.4 NFR corrections from the code (the code wins)

The issue's NFR list names 900 s TTL, a circuit breaker, and 0.5 s min
interval. The current code adds values the issue omits; §5 is normative.
Notably the kill switch is **default ON** and typo-fails-closed (only
`1`/`true`/`yes`/`on` enable; any other non-empty value disables), and the
circuit breaker is 3 consecutive upstream-health failures with a 60 s reset,
counting no deterministic 4xx/plan-gate outcomes.

---

## 3. Approved architecture

Approach **(c)** from the #3927 scoping spec: a Python HTTP client against
`https://api.gloom.sh` built on the `digifetch` transport engine. `digifetch`
stays a generic transport (no URLs, no site logic, no env reads); all
site-specific code lives in `digiquant/src/digiquant/data/gloomberb/`:

```text
models.py        Pydantic v2 inputs + wire payloads + DigifetchEnvelope[T]
normalizers.py   raw wire JSON -> typed models (permissive where unprobed)
client.py        endpoint map, HTTP, cache, breaker, kill switch, error map
entitlements.py  TOOL_ENTITLEMENTS: free | session | preview | pro
attribution.py   §7 strings + term.gloom.sh deep links
agent_tools.py   in-process dispatcher + curated pipeline subsets
mcp_server.py    FastMCP wrappers (_maybe_tool) + READ_SCOPE_TOOLS
orchestrator_tools.py  OpenAI function manifest builders
```

One client instance per `(GLOOMBERB_ENABLED, GLOOMBERB_SESSION_COOKIE)` env
pair is shared by MCP and the pipeline (`agent_tools.build_gloomberb_client`),
so pacing, cache, and breaker are shared. Every call returns
`DigifetchEnvelope[T]` whose `data` is the payload or a typed `DigifetchError`;
tools never raise.

**Adding one tool touches six registration points** (this is the checklist the
plan tasks follow):

1. `models.py` — input model, result model, `XEnvelope = DigifetchEnvelope[XResult]`.
2. `normalizers.py` — a `normalize_*` mapper (bare array or `{key: [...]}` via `_rows`).
3. `client.py` — `ENDPOINTS` entry + a method returning the envelope (uses `_validate_input`, `_request_json`, `_cached`, `_freshness`).
4. `entitlements.py` — one `TOOL_ENTITLEMENTS` row.
5. `mcp_server.py` — a `_maybe_tool` wrapper (+ `READ_SCOPE_TOOLS` for the read scope) and `orchestrator_tools.py` — a builder + the manifest list.
6. `agent_tools.py` — a `DIGIFETCH_DISPATCH` row (parity tests fail otherwise).

Existing-tool extension (the transcripts detail mode) touches 1, 2, 3, 5 and
leaves the dispatch row intact.

---

## 4. Contracts (tool surface)

### 4.1 Shared envelope and errors

Unchanged from the scoping spec §5.3 and pinned by
`models.py:350-374`: `DigifetchEnvelope[T]` =
`{source, provider_id, fetched_at, stale, delay_note, warnings, data}` with
`data` = payload or `DigifetchError{code, message, retryable}`. Error codes:
`auth_required`, `pro_required`, `not_found`, `rate_limited`,
`upstream_error`, `invalid_input`. Freshness keeps two distinct signals:
wire `stale` → `"Upstream cache stale"` (`normalizers.py:633`); free-tier
`dataSource: "delayed"` / `delayMinutes > 0` → `"Free-tier data delayed up to
15 minutes"` (`normalizers.py:634`). The new `/cloud/*` routes carry no
`dataSource`/`delayMinutes`, so `delay_note` stays null there and the
description states the platform-wide delay instead.

### 4.2 Detail-route convention (decision D3)

A detail route **of the same resource folds into the existing tool** with an
optional identifier, mirroring `digifetch_news` (`story_id` selects
`GET /news/{id}`, `models.py:556-567`). A **distinct resource gets its own
tool** (decision D4). Consequences:

| Tool | Change | Params | Client method | Endpoint | Entitlement | Cache | Envelope |
|---|---|---|---|---|---|---|---|
| `digifetch_transcripts` | **extend** | `ticker: Symbol \| None`, `transcript_id: TranscriptId \| None`, `limit: int = 20 (1–100)`; exactly one of `ticker`/`transcript_id` | `transcripts` | `GET /cloud/transcripts/{id}` when `transcript_id` set | `pro` (unchanged) | 900 s | `TranscriptsEnvelope` → `TranscriptsResult(transcripts=[Transcript])` |
| `digifetch_saved_searches` | **new** | none — parameterless, unknown fields rejected | `saved_searches` | `GET /cloud/search/saved` | `session` | 900 s | `SavedSearchesEnvelope` → `SavedSearchesResult(searches=[SavedSearch])` |

Rules for both:

- **Probe-first.** Neither detail shape is live-verified. Both are typed
  permissively (`str | int` ids, all row fields optional, extras preserved)
  until the plan's Task 1 probe records the payloads. Agree with the repo
  rule: do not tighten a deliberately permissive wire type without a live
  probe.
- **Pro mode.** `digifetch_transcripts` keeps `gated=True, pro_gated=True`;
  a free session's `Pro plan required` body (402) maps to the non-retryable
  `pro_required`, breaker-safe. Detail mode inherits this unchanged.
- **Session mode.** `digifetch_saved_searches` uses `gated=True`; without
  `GLOOMBERB_SESSION_COOKIE` it returns `auth_required` with **no HTTP
  request**. 401/402 → `auth_required` (there is no Pro gate on this route
  as probed).
- **Deep links.** Detail mode links only when `ticker` is present *or* the
  payload carries one; the ticker-mode list call keeps its
  `term.gloom.sh/?ticker=` link. Saved searches address no single listing →
  no deep link.
- **Not attributed:** nothing new here; the Yahoo-backed earnings calendar's
  `attributed=False` rule is untouched.
- **No new storage.** Both are enrichment reads; nothing is persisted
  (repo rule: the platform stores it).

**`digifetch_transcripts` detail-mode input sketch** (normative for the plan):

```python
TranscriptId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

class TranscriptsInput(_InputModel):
    ticker: Symbol | None = None
    transcript_id: TranscriptId | None = None
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "TranscriptsInput":
        if (self.ticker is None) == (self.transcript_id is None):
            raise ValueError("provide exactly one of ticker or transcript_id")
        return self
```

**`digifetch_saved_searches` models sketch:**

```python
class SavedSearchesInput(_InputModel):
    """The Cloud saved-searches route takes no parameters."""

class SavedSearch(_CamelModel):
    id: str | int | None = None
    name: str | None = None
    query: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

class SavedSearchesResult(_CamelModel):
    searches: list[SavedSearch] = Field(default_factory=list)

SavedSearchesEnvelope = DigifetchEnvelope[SavedSearchesResult]
```

---

## 5. Normative values (read from the code, 2026-09-16)

| Value | Exact | Source |
|---|---|---|
| Cache TTL (client-wide, all tools) | `900.0` s | `client.py:161` (`DEFAULT_CACHE_TTL_SECONDS`) |
| Cache bound | 256 entries, expired evicted on access | `client.py:168` (`DEFAULT_CACHE_MAX_ENTRIES`) |
| Min request interval | `0.5` s | `client.py:158` (`DEFAULT_MIN_INTERVAL_SECONDS`) |
| Circuit breaker | 3 consecutive upstream-health failures → open; `60.0` s reset; half-open probes allowed | `client.py:162-163`, `:2114-2141` |
| Breaker exemptions | `auth_required` / `pro_required` / `not_found` / `invalid_input` and the 13F proxied-4xx path never count | `client.py:2249-2277`, `:341-351` |
| 429 `Retry-After` | honored only `0 < s <= 5.0` (bounded sleep); larger surfaced, not slept | `client.py:166`, `:2178-2194` |
| Kill switch | `GLOOMBERB_ENABLED`, **default ON**; only `1/true/yes/on` enable (case-insensitive); any other non-empty value disables | `client.py:248-272` |
| Market search clamp | `SEARCH_LIMIT_CAP = 10`, flagged via `data.limit_clamped` | `client.py:170`, `:1046-1070` |
| `digifetch_cds.days` | 1–90 client-side (upstream would 400) | `models.py:595` |
| `digifetch_research_search` | `limit` 1–100, `offset` 0–10 000 | `models.py:599-603` |
| `digifetch_transcripts.limit` | 1–100 | `models.py:613` |
| `digifetch_econ_series.limit` | 1–1 000 | `models.py:577-581` |
| `digifetch_ticker_tweets` / `tweet_search` | `limit` 1–200, `hours` 1–720 (client filters/slices; upstream ignores both) | `models.py:627-641` |
| `digifetch_13f_funds` | `what` ∈ search/top/tickers/holders; `limit` 1–200, `offset` 0–10 000, `tickers` ≤50; `quarter` `YYYYQn`; `cik` zero-padded to 10 digits | `models.py:670-762` |
| `digifetch_13f_holdings` | `what` ∈ filings/forms/form; `limit` 1–200; `accession_number` normalized to dashed 18-digit form; `has_more = len(rows) >= limit`; upstream caps one form at 20 000 rows | `models.py:703-762`; `normalizers.py:1172-1188` |
| `digifetch_shiller.limit` | 1–2 000 (default 240) | `models.py:770-773` |
| `digifetch_short_interest.years` | 1–10 client-side | `models.py:814-818` |
| Price resolution×range caps | `RESOLUTION_MAX_RANGE` (5m→1wk, 15m→1mo, 1h→3mo, 1d→5y, 1wk→5y, 1mo→ALL) + `RESOLUTION_MAX_RANGE_LABELS`; out-of-contract = `invalid_input`, never clamped | `models.py:244-265` |
| History window escape hatch | `start_date`/`end_date` ISO `YYYY-MM-DD`, mutually exclusive with `range`, sends `rangeKey=ALL` (#4100) | `models.py:387-468`, `client.py:613-629` |
| Attribution | `"Sourced from Gloomberb"` ; `"Data delayed up to 15 minutes"` ; terminal `https://term.gloom.sh/?ticker=` | `attribution.py:21-39` |
| Delay semantics | prices ~15 min delayed; news ~12 h delayed (headline freshness is upstream's) — descriptions must state both | #4110 body; shipped descriptions (`mcp_server.py:896-1534`) |
| Entitlement vocabulary | `free` \| `session` \| `preview` \| `pro` | `entitlements.py:55-96` |

No value in this table may be relaxed without a spec amendment and a live
probe; no value may be tightened without one either (permissive-wire rule).

---

## 6. Coverage matrix (per endpoint)

Entitlement column: F = free/anonymous, S = session cookie, P = preview
(session, free tier gets labeled preview), Pro = session + Gloomberb Pro.
Phase: the shipped PR cohort or the remaining phase.

### Shipped — original 13 (#4069, PR #4085)

| Tool | Endpoint(s) | Params (MCP surface) | Envelope | Ent. | Phase |
|---|---|---|---|---|---|
| `digifetch_quote` | `GET /market/quote` | `symbol`, `exchange?` | `QuoteEnvelope` | F | 0 |
| `digifetch_quotes_batch` | `POST /market/quotes/batch` | `symbols` 1–20 | `QuotesBatchEnvelope` | F | 0 |
| `digifetch_price_history` | `GET /market/history` | `symbol`, `resolution`, `range?`, `start_date?`/`end_date?`, `exchange?` | `PriceHistoryEnvelope` | F | 0 |
| `digifetch_ticker_financials` | `GET /market/financials` | `symbol`, `exchange?`, `extended_statements` | `TickerFinancialsEnvelope` | F | 0 |
| `digifetch_options_chain` | `GET /market/options` | `symbol`, `exchange?`, `expiration?` | `OptionsChainEnvelope` | F | 0 |
| `digifetch_sec_filings` | `GET /cloud/sec/filings`, `/filing/documents`, `/filing/content` | `ticker`, `what`, `count=15`, `cik?`, `accession?`, `form?` | `SecFilingsEnvelope` | F | 0 |
| `digifetch_holders` | `GET /market/holders` | `symbol`, `owner_type` | `HoldersEnvelope` | S | 0 |
| `digifetch_analyst_research` | `GET /market/analyst` | `symbol`, `limit=20` | `AnalystResearchEnvelope` | S | 0 |
| `digifetch_corporate_actions` | `GET /market/corporate-actions` | `symbol` | `CorporateActionsEnvelope` | S | 0 |
| `digifetch_earnings_calendar` | Yahoo via `yfinance` (no Cloud route; **not attributed**) | `symbols`, `horizon_days=90` | `EarningsCalendarEnvelope` | F | 0 |
| `digifetch_exchange_rate` | `GET /market/exchange-rate` | `from_currency`, `to_currency="USD"` | `ExchangeRateEnvelope` | F | 0 |
| `digifetch_search` | `GET /market/search` | `query`, `limit=10` (clamped to 10) | `SearchEnvelope` | F | 0 |
| `digifetch_news` | `GET /news`, `GET /news/{id}` | `feed`, `ticker?`, `story_id?`, `limit=20` | `NewsEnvelope` | F | 0 |

### Shipped — phase 1 cohort (#4112)

| Tool | Endpoint(s) | Params | Envelope | Ent. | Phase |
|---|---|---|---|---|---|
| `digifetch_econ_calendar` | `GET /cloud/econ/calendar` | none | `EconCalendarEnvelope` | F | 1 |
| `digifetch_econ_series` | `GET /cloud/econ/series/{seriesId}` | `series_id`, `limit=100` (≤1000), `sort_order` | `EconSeriesEnvelope` | F | 1 |
| `digifetch_yield_curve` | `GET /cloud/econ/yield-curve` | none | `YieldCurveEnvelope` | F | 1 |
| `digifetch_cds` | `GET /cloud/credit/cds` | `issuer?` (≤200), `days=30` (1–90), `limit=100` (≤200) | `CdsEnvelope` | F | 1 |
| `digifetch_research_search` | `GET /cloud/search` | `query` (≤200), `limit=10` (≤100), `offset=0` (≤10 000) | `ResearchSearchEnvelope` | S | 1 |
| `digifetch_congress_trades` | `GET /cloud/congress/house` | `year?`, `limit=50` (≤200) | `CongressTradesEnvelope` | F | 1 |
| `digifetch_transcripts` | `GET /cloud/transcripts` | `ticker`, `limit=20` (≤100) | `TranscriptsEnvelope` | Pro | 1 |

### Shipped — phase 2 cohort (#4119)

| Tool | Endpoint(s) | Params | Envelope | Ent. | Phase |
|---|---|---|---|---|---|
| `digifetch_statements` | `GET /market/statements` | `symbol`, `period`, `exchange?` | `StatementsEnvelope` | S | 2 |
| `digifetch_ticker_tweets` | `GET /news/tweets` | `ticker`, `limit=50` (≤200), `hours?` (1–720), `include_replies` | `TweetsEnvelope` | S | 2 |
| `digifetch_tweet_search` | `GET /news/tweets/search` | `query`, `query_type`, `limit=50` (≤200), `hours?` (1–720) | `TweetsEnvelope` | S | 2 |
| `digifetch_venues` | `GET /market/venues` | none | `VenuesEnvelope` | F | 2 |
| `digifetch_screener` | `GET /market/screener` | `category`, `count=25` (1–50), `mode` | `ScreenerEnvelope` | Pro | 2 |
| `digifetch_13f_funds` | `GET /cloud/sec/13f/{funds,topfunds,tickers,holders}` | `what`, `query?`, `quarter?`, `tickers?`, `cusip?`, `period_of_report?`, `limit=25`, `offset=0` | `Funds13FEnvelope` | F | 2 |
| `digifetch_13f_holdings` | `GET /cloud/sec/13f/{filings,forms,form}` | `what`, `cik?`, `accession_number?`, `from_date?`, `to_date?`, `limit=50`, `offset=0` | `Holdings13FEnvelope` | F | 2 |

### Shipped — phase 3 cohort (#4126)

| Tool | Endpoint(s) | Params | Envelope | Ent. | Phase |
|---|---|---|---|---|---|
| `digifetch_shiller` | `GET /cloud/econ/shiller` | `limit=240` (≤2000) | `ShillerEnvelope` | F | 3 |
| `digifetch_proxy_statements` | `GET /public/proxies/{ticker}[/{year}]` | `ticker`, `what`, `year?` | `ProxyStatementsEnvelope` | F | 3 |
| `digifetch_filing_events` | `GET /public/events/{ticker}` | `ticker`, `limit=20` (≤200) | `FilingEventsEnvelope` | F | 3 |
| `digifetch_risk_reports` | `GET /public/risks/{ticker}[/{year}]` | `ticker`, `what`, `year?` | `RiskReportsEnvelope` | F | 3 |
| `digifetch_short_interest` | `GET /market/short-interest` | `symbol`, `years=3` (1–10) | `ShortInterestEnvelope` | S | 3 |
| `digifetch_equity_diagnostic` | `POST /research/equity-diagnostic` | `symbol`, `exchange?`, `mode` | `EquityDiagnosticEnvelope` | P | 3 |

### Residual — phase 4a (this spec's plan)

| Tool | Endpoint(s) | Params | Envelope | Ent. | Phase |
|---|---|---|---|---|---|
| `digifetch_transcripts` (extended) | `GET /cloud/transcripts/{id}` | `transcript_id` (exactly one of `transcript_id`/`ticker`) | `TranscriptsEnvelope` | Pro | 4a |
| `digifetch_saved_searches` | `GET /cloud/search/saved` | none | `SavedSearchesEnvelope` | S | 4a |

### Deferred — phase 4b/4c (no endpoint work)

| Pane | Disposition | Reference |
|---|---|---|
| Correlation / relationship graph; world indices / FX matrix / futures; volatility / credit conditions; dividend yield | **Client-side composition** over `digifetch_price_history`, `digifetch_quote`, `digifetch_econ_series` — no new fetch; belongs to a UX/agent task if ever built | `ARCHITECTURE.md:1332-1340` |
| Treasury auctions (`api.fiscaldata.treasury.gov`) | **New external dependency → blocked**; new issue + human gate | `ARCHITECTURE.md:1341` |
| Prediction markets (kelly-sizer local model) | No data endpoint exists — out of scope permanently | `ARCHITECTURE.md:1342` |
| Market movers / scanner (websocket stream) | Screener shipped; the live stream is not an HTTP read — out of scope | `ARCHITECTURE.md:1343` |
| Surface integration (deep links, attribution UI) | #4098 | issue body |

---

## 7. Sequencing and decisions

### Phases

| Phase | Scope | Status | Plan |
|---|---|---|---|
| 0 | 13-tool #4069 contract | shipped #4085 | #4069 closed |
| 1 | macro/econ + credit + research search + congress + transcripts list | shipped #4112 | already executed |
| 2 | statements + tweets + venues + screener + 13F | shipped #4119 | already executed |
| 3 | discoverable plugin panes (valuation/executives/risk/events/short interest/equity diagnostic) + entitlement layer #4135 | shipped #4126/#4135 | already executed |
| **4a** | **residual endpoints: transcripts detail + saved searches** | **open** | **`docs/superpowers/plans/2026-09-16-digifetch-coverage-expansion.md`** |
| 4b | plugin panes without a shipped endpoint (composition vs blocked third-party vs websocket) | deferred | own spec + plan at pickup (or a decision to drop); no non-gloomberb deps allowed without a new issue + human gate |
| 4c | digiquant surface integration | owned by #4098 | plan lives with #4098 |

**Plan split (writing-plans scope check).** Phase 4a is its own shippable
subsystem and gets the one executable plan in this pair. Phases 4b and 4c are
separate subsystems and get their own plans at pickup: 4b first needs a
discovery/decision pass (the remaining panes are not endpoint-uniform), and
4c's deliverable lives in the dashboard/digichat surfaces owned by #4098. No
plan is written for shipped phases 0-3 — the code and tests are their record.

### Decisions

- **D1 — Shipped phases are recorded, not re-planned.** #4112/#4119/#4126/#4135
  merged the issue's "ready to add" matrix plus six extra endpoints; the issue
  body is stale and §2.1 is the corrected map. No rewrite of shipped tools.
- **D2 — Residual scope is exactly two endpoints** (`/cloud/transcripts/{id}`,
  `/cloud/search/saved`) and it is phase 4a. Everything else in the matrix is
  either shipped or explicitly classified below.
- **D3 — Transcripts detail folds into `digifetch_transcripts`** via an
  optional `transcript_id`, exactly one of `ticker`/`transcript_id`, following
  the `digifetch_news` `story_id` precedent. Rationale: one resource, one
  discoverable tool, additive input schema, and the existing `pro` entitlement
  and deep-link behavior carry over. A separate `digifetch_transcript` tool
  would double the discovery surface for the same resource family.
- **D4 — Saved searches gets its own tool** (`digifetch_saved_searches`),
  because it is a distinct resource (the caller's saved search definitions),
  not a variant of a search result set. Parameterless, `session` entitlement,
  no deep link. It is *not* added to the pipeline subsets (`EQUITY_TOOLS` /
  `MACRO_TOOLS` / `PM_TOOLS`) — prompt budget; it remains MCP-first.
- **D5 — Plugin-pane disposition is three-way, and only one class is future
  work.** Composition panes (correlation, world indices/FX/futures,
  volatility/credit, dividend yield) need no new fetch and are deferred to a
  UX/agent task; the fiscaldata/prediction-market/scanner panes are blocked
  (new external dependency, no endpoint, websocket) and stay out of #4110. The
  `ARCHITECTURE.md:1330-1346` rationale is confirmed and extended here.
- **D6 — No new storage, no attribution changes.** All tools stay read-only
  enrichment; nothing is persisted; the §7 attribution/deep-link rules and the
  earnings-calendar non-attribution exception are unchanged.
- **D7 — Human gate.** The shipped `api.gloom.sh` dependency means phase 4a is
  *not* new network exposure. The gate applies to any future non-gloomberb
  dependency only. Any such need = new issue + explicit human sign-off.
- **D8 — Probe-first for both residual shapes.** The plan's Task 1 runs live
  probes and records the payloads; if a route 404s or is renamed, the task
  stops and amends this spec instead of shipping a speculative client.

---

## 8. Verification (measurable)

All commands run in the worktree, offline (MockTransport) except the Task 1
probe:

```bash
# 1. The residual endpoints exist in the endpoint map / client
grep -n "transcripts" digiquant/src/digiquant/data/gloomberb/client.py
grep -n "saved_searches" digiquant/src/digiquant/data/gloomberb/client.py

# 2. Both tools are registered on all three surfaces and declared
grep -c "digifetch_saved_searches" digiquant/src/digiquant/mcp_server.py          # 2 (READ_SCOPE_TOOLS + wrapper)
grep -c "digifetch_saved_searches" digiquant/src/digiquant/orchestrator_tools.py  # 2 (builder name + manifest list)
grep -c "digifetch_saved_searches" digiquant/src/digiquant/data/gloomberb/agent_tools.py    # 1 (DIGIFETCH_DISPATCH)
grep -c "digifetch_saved_searches" digiquant/src/digiquant/data/gloomberb/entitlements.py   # 1 (TOOL_ENTITLEMENTS)

# 3. Tests (RED first, then GREEN) — exact targets from the plan
pytest tests/dq/data/test_gloomberb_models.py tests/dq/data/test_gloomberb_normalizers.py \
       tests/dq/data/test_gloomberb_client.py tests/dq/test_mcp_gloomberb_tools.py \
       tests/dq/data/test_gloomberb_agent_tools.py -m unit -q
pytest tests/dq/test_mcp_server_scope.py -m unit -q

# 4. Lint / docs
ruff check digiquant/ && ruff format --check digiquant/
make doc-check
```

Expected: every grep exact; the unit sweep green; parity tests
(`test_dispatch_table_covers_every_schema_and_matches_its_parameters`,
`test_dispatch_link_and_attribution_match_the_mcp_wrappers`,
`test_schemas_are_the_manifest_entries_for_the_entitled_names`) green with the
new tool in each surface.

---

## 9. Risks and fallbacks

| Risk | Mitigation |
|---|---|
| `/cloud/transcripts/{id}` or `/cloud/search/saved` shapes differ from the sketches, or a route is absent in the deployed API | Probe-first Task 1 with a go/no-go; permissive wire types + extras; spec amended before implementation code is written |
| Free session cannot reach `/cloud/transcripts/{id}` (Pro gate) | Already the expected behavior: typed `pro_required`, breaker-safe; tests assert the 402/text-body path in detail mode |
| `/cloud/search/saved` is Pro-gated rather than merely session-gated | Probe records the status; if Pro, the entitlement declaration becomes `pro` (one-row change) and the plan's test expects `pro_required` instead of `auth_required` |
| Adding a tool drifts the four surfaces (MCP/manifest/dispatch/entitlements) | The existing parity tests fail on drift; the plan updates all six registration points in one task |
| `gloomberb` upstream changes break the family | Unchanged from the scoping spec: typed `upstream_error` surface, kill switch, breaker; MIT source vendorable as a last resort |
| Scope creep into non-gloomberb panes via "one more source" | D5/D7: blocked; new issue + human gate required |
| The issue body's stale phase numbering misleads an executor | §2.1 is the corrected map; the plan header repeats it |

---

## 10. Out of scope

- Implementation of phases 4b/4c; the plans for those are authored at pickup.
- Any change to the 33 shipped tools beyond the additive `transcripts` input
  extension.
- New external dependencies, new storage, pipeline-primary sourcing.
- Frontend/digichat rendering of the data (§4098).
- Post-deploy verification of the family (owned by #4101) and the cookie
  runbook (owned by #4099).

---

## 11. Open questions

1. **Transcripts detail payload shape** — does `/cloud/transcripts/{id}` return
   the full transcript text (sections/segments), a wrapped
   `{transcript: {...}}`, or the same list-row shape? Task 1 probe decides; the
   plan's permissive model tolerates all three.
2. **Saved searches semantics** — "saved searches" (definitions) vs "saved
   search results"? The name and the issue's parenthetical suggest definitions;
   the probe freezes it. If it turns out to be results, rename to
   `digifetch_saved_search_results` in the spec amendment.
3. **Pro gating of `/cloud/search/saved`** — unknown until probed (affects the
   entitlement row only).
4. **Phase 4b worth** — whether any composition pane is worth building as an
   agent-side helper; deferred to that phase's spec, not answered here.
5. **Pipeline subsets** — should `digifetch_saved_searches` ever join a
   curated subset? D4 says no for now; revisit if a pipeline use case appears.
