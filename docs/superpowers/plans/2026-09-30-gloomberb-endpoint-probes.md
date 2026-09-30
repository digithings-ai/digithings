# Gloomberb Endpoint Probe Verdicts (Task 4, tracks #4837)

Source-first probe of every PROBE item in
`2026-09-30-gloomberb-function-matrix.md`. Clone sources (read 2026-09-30):
`gloom-sh/gloomberb` plus `gloom-substack`, `gloom-ipo-calendar`,
`gloom-market-halts`, `gloom-hackernews`, `gloom-fear-greed`, `gloom-polls`,
`gloom-ibkr-gateway`, `gloom-simplefin`, `gloom-public`, `gloom-robinhood`,
`gloom-byok-ai`, `gloom-prediction-markets`.

**No live HTTP calls were made.** There is no recorded operator approval for
any host, so every verdict below comes from route shapes in the
source-available TypeScript (`src/api-client/`, builtin plugin `client.ts` /
`model.ts`, `docs/`). Every row carries a `Live: unverified` marker. No
secrets were used or pasted (none needed; probes are shape reads).

Base URL: `https://api.gloom.sh` (`src/api-client/request.ts:24`
`DEFAULT_API_URL`). Auth transport: Cloud session cookie
`__Secure-gloomberb.session_token` / `gloomberb.session_token`
(`src/api-client/session-cookie.ts:1-9`); sign-in is email+password, device
flow, or browser handoff (`src/api-client/auth.ts:74-127,205-213`); plan comes
from `/auth/get-session` + `/account/profile`
(`src/api-client/plan-rules.ts:4-15`). 401/403 = session problem
(`src/api-client/errors.ts:39`); Pro-gated search returns 402
(`src/api-client/data.ts:573-586`).

Entitlement shorthand used below: `open` (works signed out), `session`
(signed-in Cloud account), `verified` (signed in + verified email),
`pro` (paying Pro or active trial, `hasProAccess`,
`src/api-client/plan-rules.ts:66-71`). Free-tier quotes/news are delayed
(15m quotes, 12h news, `src/api-client/plan-rules.ts:31-34`). Guesses are
marked as such; live status is unverified throughout.

## Verdicts

### TAS — Time and sales — ROUTE

- Method + path: `GET /cloud/tape/{symbol}?exchange={exchange}`
  (`CloudDataApi.getCloudTape`, `src/api-client/data.ts:355-357`), plus live
  socket `subscribeTape` with snapshot resync
  (`src/plugins/builtin/time-sales/use-tape.ts:7-57`,
  `src/api-client/index.ts:667`).
- Params: bare symbol (path), `exchange` (query, required).
- Entitlement guess: `session` — the pane renders a sign-in wall when the
  session is required (`src/plugins/builtin/time-sales/pane.tsx:93`); feed is
  `sip` realtime for Pro, `delayed_sip` (900s) otherwise
  (`src/api-client/tape.ts:22-42`, `pane.tsx:88`,
  `docs/research-data.md:619`).
- Shape: `TapeSnapshot` — `trades[]` (`id/timestamp/price/size/exchange/
  conditions[]/tape`), session high/low, capacity/drop/cancel counters
  (`src/api-client/tape.ts:1-42`).
- Live: unverified.

### QR — Quote recap — ROUTE (shared with TAS)

- QR is the NBBO tab of the same time-sales pane, not a separate endpoint:
  `tab: "trades"` (TAS) vs `tab: "quotes"` (QR) over one tape subscription
  (`src/plugins/builtin/time-sales/index.tsx:6-16`).
- Same method + params + entitlement as TAS; shape is the `quotes[]` array of
  the same `TapeSnapshot` (`bid/ask/bidSize/askSize` in round lots,
  venues, conditions, spread context, `src/api-client/tape.ts:10-21`).
- Live: unverified.

### EE — Earnings estimates — NO-ROUTE, fallback: compose

- No dedicated Cloud EE route exists. The EE pane is the `earnings-estimates`
  variant of the corporate-actions pane
  (`src/plugins/builtin/research/index.tsx:135-145`), fed by
  `loadEventSources`: `getCorporateActions` + `getAnalystResearch` +
  `getTickerFinancials` together, each failing independently
  (`src/plugins/builtin/research/event-sources.ts:46-64`).
- Those are DONE routes (`GET /market/corporate-actions`, `/market/analyst`,
  `/market/financials`, `src/api-client/data.ts:237-287`); columns are
  Q/annual EPS + revenue (`event-sources.ts:16-27`).
- Verdict: no new transport; compose over shipped tools. Live: unverified.

### EMM — Estimate revisions — ROUTE

- Method + path: `GET /cloud/research/estimates/{symbol}?exchange={exchange}`
  (`CloudDataApi.getCloudEstimateRevisions`, `src/api-client/data.ts:172-174`).
- Params: symbol (path), exchange (query). (Pane shortcut in code is `EM`
  with alias `EEO`, `src/plugins/builtin/estimate-revisions/index.tsx:59-61`;
  docs prefix is EMM — same pane.)
- Entitlement guess: `session` (Cloud research route; no Pro-gate evidence in
  source).
- Shape: `EstimateRevisionsPayload` — per-period current/recorded/lookback
  observations (source `yahoo` / `yahoo-eps-trend`), 7/30d revision breadth,
  surprises, guidance, coverage/gaps
  (`src/api-client/estimate-revisions.ts:16-113`).
- Live: unverified.

### SIV — Daily short volume — ROUTE

- Method + path: `GET /cloud/short-volume?symbol={sym}&scope={nms|otc}`
  (`CloudDataApi.getCloudShortVolume`, `src/api-client/data.ts:418-421`).
- Params: symbol, scope (`nms` default, `otc`).
- Entitlement guess: `session`.
- Shape: `ShortVolumePayload` — FINRA-sourced daily rows
  (`shortVolume/shortExemptVolume/totalVolume/ratioPercent/markets/
  sourceUrl`), latest row with change + percentile, coverage window, warnings
  (`src/api-client/short-volume.ts:1-60`).
- Live: unverified.

### JOBS — Hiring — ROUTE

- Methods + paths (`src/api-client/paths.ts:263-296`,
  `src/api-client/data.ts:472-485`):
  - `GET /cloud/jobs/{ticker}[?name=]` → summary or `{status:"pending"}`
  - `GET /cloud/jobs/{ticker}/postings?[limit&offset&...]` →
    `{postings[], total}`
  - `GET /cloud/jobs?[limit&offset]` → hiring movers
    (`{asOf, covered, movers[]}` with `openCount/employeeCount/change30d/
    new7d/topFunction`, `src/api-client/types.ts:699-723`).
- Params: ticker (path, issuer-normalized), optional company name; postings
  pagination params (`CloudJobsPostingsParams`, `paths.ts:282-290`).
- Entitlement guess: `session`.
- Live: unverified.

### INS — Insider transactions — NO-ROUTE, fallback: compose

- No dedicated insider endpoint. The INS pane loads SEC filings and keeps
  Form 4 / 4-A (`isInsiderForm`, `src/plugins/builtin/insider/
  insider-data.ts:34-40`), then parses each filing's XML content
  (`src/plugins/builtin/insider/client.ts:5-46`).
- Composition path over DONE routes: `getCloudSecFilings` (`/cloud/sec/
  filings`, `src/api-client/data.ts:544-548`) filtered to `4`/`4/A`, then
  `getCloudSecFilingContent` (`/cloud/sec/filing/content`), whose response
  already carries a parsed `form4` block (`reportedName/title/
  transactionType P|S|A|D/shares/pricePerShare/totalValue`,
  `src/api-client/types.ts:1095-1110`).
- Verdict: no new transport; compose over shipped SEC tools. Live: unverified.

### CBR — Central bank rates — ROUTE

- Method + path: `GET /cloud/econ/central-bank-rates`
  (`CloudDataApi.getCloudCentralBankRates`, `src/api-client/data.ts:367-369`).
- Params: none.
- Entitlement guess: `session`.
- Shape: `CentralBankRatesPayload.rows[]` — policy rate or target range,
  FRED/BIS provenance with `sourceSeriesIds`, percentiles + history,
  next-meeting dates (US FOMC schedule only), stale/confirmed states
  (`src/api-client/central-bank-rates.ts:1-40`,
  `docs/research-data.md:220`).
- Live: unverified.

### CRD — Credit spreads — ROUTE (FRED proxy), fallback: compose board

- No `/cloud/credit/*` spreads route; the CRD pane (`shortcut CRD`,
  "ICE BofA US corporate option-adjusted spreads from FRED",
  `src/plugins/builtin/credit-conditions/index.tsx:150-159`) reads FRED
  through `getCloudFredSeries` (`src/plugins/builtin/credit-conditions/
  client.ts:89`).
- Method + path: `GET /cloud/econ/series/{seriesId}` (`src/api-client/
  paths.ts:189-201`, `data.ts:334-341`) with the six board ids
  (`src/plugins/builtin/credit-conditions/model.ts:4-10`): `BAMLC0A0CM`
  (US IG), `BAMLC0A1CAAA`, `BAMLC0A2CAA`, `BAMLC0A3CA`, `BAMLC0A4CBBB`,
  `BAMLH0A0HYM2` (US HY).
- Verdict: Cloud route exists (FRED proxy); board is a composition over
  `econ_series`. Live: unverified.

### CDX — Index CDS — ROUTE

- Method + path: `GET /cloud/credit/cdx[?days=]` (`cloudCreditBoardPath`,
  `src/api-client/paths.ts:219-223`; `getCloudCdxBoard`,
  `src/api-client/data.ts:454-456`).
- Params: optional `days` (history depth).
- Entitlement guess: `session`.
- Shape: `CdxBoardPayload` — 5Y on-the-run IG/HY/EM + iTraxx Main/Crossover
  (spread- vs price-quoted), daily `points[]` with on-the-run maturity,
  built from DTCC dissemination (`src/api-client/credit-boards.ts:1-40`).
- Live: unverified.

### SOVR — Sovereign CDS — ROUTE

- Method + path: `GET /cloud/credit/sovr[?days=]` (same builder + client as
  CDX, `paths.ts:219-223`, `data.ts:458-460`).
- Params: optional `days`.
- Entitlement guess: `session`.
- Shape: `SovrBoardPayload` — per-sovereign 5Y spread (bp), 1W/1M changes,
  daily points, widest-1M-move first (`credit-boards.ts:42-60`).
- Live: unverified.

### HILO — New highs and lows — NO-ROUTE (REST), fallback: OUT

- The HILO scanner is socket-only: `subscribeScanner("hilo")`
  (`src/api-client/index.ts:668`, `socket.ts:53`) feeding
  `ScannerHiloPayload` — 30s/1m/5m windows plus highs/lows lists
  (`src/api-client/types.ts:1467-1493`). No REST equivalent exists in
  `api-client/`; headless consumption also goes through the socket
  (`src/plugins/builtin/scanner/headless.ts:87-119`).
- Gating note: free accounts get the delayed (15m) scanner instance, Pro gets
  realtime (`ScannerAccessInfo`, `types.ts:1476-1481`) — but both are socket
  tiers, unusable from a request/response tool.
- Verdict: NO-ROUTE over HTTP; OUT (a streaming scanner has no tool-shaped
  equivalent; 52-week extremes are already in quotes/screener, session
  extremes are not reconstructible). Live: unverified.

### FLOW — Options flow — ROUTE, Pro-gated

- Live: socket `subscribeScanner("flow")` → `ScannerFlowPayload.events[]`
  (`id/at/underlying/contract C|P/strike/expiry/side/kind
  sweep|block|split|trade/size/price/premium/vol/OI/volOi/iv`,
  `src/api-client/types.ts:1495-1518`).
- Recorded: `GET /market/scanner/flow/history?{before,limit,minPremium,
  right,kind,minVolOi,maxExpiryDays,symbols}` → `{events[], hasMore}`
  (`CloudDataApi.getScannerFlowHistory`, `data.ts:371-374`;
  `ScannerFlowHistoryQuery/Page`, `types.ts:1520-1537`; pane loader
  `src/plugins/builtin/scanner/flow-history.ts:36-37`).
- Gating (Pro + auth, explicit): FLOW is "the one scanner with no delayed
  tier"; refusal reasons are `auth_required` (signed out) or `pro_required`
  (`src/plugins/builtin/scanner/denied.tsx:1-18`,
  `feed.ts:17-19,75-83`); history is labeled "(Pro)" at the client
  (`data.ts:371`); alerts docs confirm "(Pro)" with $50K+ prints over ~500
  premium-ranked contracts (`docs/research-data.md:436-445`,
  `docs/usage.md:310-323`).
- Verdict: Cloud tool reading the recorded-history route; fail closed on
  denial (surface `pro_required`/`auth_required`, never empty). Live socket
  itself is out of tool shape. Live: unverified.

### COT — CFTC positioning — ROUTE

- Methods + paths (`src/api-client/data.ts:347-353`):
  - `GET /cloud/cot/board?report={legacy|disaggregated}&traderClass={...}`
  - `GET /cloud/cot/contracts/{code}?report={...}`
- Params: `report` family; `traderClass` one of noncommercial/commercial/
  producer/swap/managed-money/other-reportable/nonreportable
  (`src/api-client/cot.ts:1-8`).
- Entitlement guess: `session`.
- Shape: futures-only CFTC rows per contract (Tuesday as-of, no publication
  timestamp), class long/short/spreading + net + 1Y/3Y percentiles
  (`cot.ts:28-60`); pane maps e.g. 3M SOFR → code `134741`
  (`src/plugins/builtin/cot/model.ts:19`).
- Live: unverified.

### CRYP — Crypto board — ROUTE

- Method + path: `GET /cloud/crypto/markets`
  (`CloudDataApi.getCloudCryptoMarkets`, `src/api-client/data.ts:363-365`).
- Params: none. Pane refreshes every 15s; rows additionally ride the market
  socket for live quotes (`docs/research-data.md:665-669`).
- Entitlement guess: `session`.
- Shape: `CryptoMarketsPayload` — up to 100 coins + own stablecoin tab
  (wrapped/staked/bridged dupes and <$1M 24h-volume pairs excluded),
  price/change/day range/24h volume/market cap/supply/52w range/year-ago
  price/30 daily closes; `source:{name,url}` is server-declared — no vendor
  asserted here (`src/api-client/crypto-markets.ts:1-50`).
- Verdict: coin-list source is the Cloud route itself. Live: unverified.

### VCA — Volatility rich/cheap — ROUTE

- Method + path: `GET /cloud/iv/screen?symbols={csv}` via the prefix-scoped
  client (`loadIvScreen`, `src/plugins/builtin/iv-history/client.ts:87-89`;
  `impliedVolatility(path)`, `data.ts:157-160`).
- Params: comma-joined bare US symbols (listing exchange stripped,
  `client.ts:80-81`).
- Entitlement guess: `session` (no Pro-gate evidence in source — no
  `pro_required`/402 handling and no `usePlanAccess` in the iv-history
  plugin; stored-history route like the other `/cloud/iv/*` reads).
- Shape: `IvScreenPayload.rows[]` — per-symbol ready/queued status,
  iv30/iv90 stats (value/date/rank/percentile), latest reading, 25-delta
  skew (`client.ts:60-68`); screen universe defaults to ETFs or a custom
  list (`index.tsx:36-41`).
- Coverage note: stored daily history covers US option underlyings from
  February 2024 (`docs/research-data.md:521`). Live: unverified.

### HIVG — Implied volatility history — ROUTE (IV-history)

- Method + path: `GET /cloud/iv/history?symbol={sym}&days={n, default 1100}`
  (`loadIvHistory`, `src/plugins/builtin/iv-history/client.ts:83-86`).
- Params: bare US symbol, days of stored history.
- Entitlement guess: `session` (same no-Pro-gate-evidence position as VCA;
  the pane pairs stored IV with price-history HV computed client-side,
  `client.ts:107-130`).
- Shape: `IvHistoryPayload` — coverage status (ready/backfilling/queued/
  unavailable), iv7/30/60/90/180/365 term points per session, iv30/iv90 rank
  + percentile stats, latest reading, warnings (`client.ts:12-59`); pane
  description "30 and 90-day ATM IV since 2024 ... with IV rank and
  percentile" (`index.tsx:26-31`).
- Live: unverified.

### OVDV — Volatility surface — ROUTE (stored) + compose (live)

- Live surface is a client-side build over the options-chain coordinator plus
  Treasury curve (`loadVolatilitySurface`,
  `src/plugins/builtin/vol-surface/client.ts:114-243`; yield curve from
  `getCloudYieldCurve`, `client.ts:49-59`) — composition-shaped, no single
  surface route.
- Stored close surfaces: `GET /cloud/iv/surface-dates?symbol=` and
  `GET /cloud/iv/surface?symbol=&date=` (`loadSurfaceDates`,
  `loadStoredSurface`, `src/plugins/builtin/iv-history/client.ts:90-96`),
  rendered through the same views (`vol-surface/stored.ts:66-82`).
- Verdict: Cloud route exists for dated stored surfaces; a live-surface tool
  would compose over `options_chain` + `yield_curve`. Entitlement guess:
  `session` for both. Live: unverified.

### HVG / HVT — Realized volatility + cone — NO-ROUTE, fallback: compose

- No dedicated Cloud route. Both tabs of the realized-vol pane
  (`HVG` graph / `HVT` cone, `headless.ts:8-14`) compute client-side:
  5Y daily history → close-to-close/Parkinson/Garman-Klass/Rogers-Satchell/
  Yang-Zhang estimators over 20/30-session (graph) or seven-window (cone)
  distributions (`loadRealizedVolatilityHistory`,
  `src/plugins/builtin/realized-vol/client.ts:41-56`;
  `docs/research-data.md:322`).
- Current-ATM-IV overlay reuses the OVDV chain loader, never a stored IV
  line (`docs/research-data.md:324`).
- Verdict: compose over `price_history` (+ `options_chain` for the ATM
  reference). Live: unverified.

### DDIS — Debt maturities — ROUTE

- Method + path: `GET /cloud/debt-maturities?symbol={sym}`
  (`CloudDataApi.getCloudDebtMaturities`, `src/api-client/data.ts:384-387`).
- Params: symbol.
- Entitlement guess: `session`.
- Shape: `DebtMaturitiesPayload` — US-GAAP debt facts with accession/filed/
  form provenance, total principal, next-12M/3Y shares, interest expense +
  borrowing cost, per-filing history points
  (`src/api-client/debt-maturities.ts:1-60`).
- Live: unverified.

### MOST-trending (incl. pre-market / after-hours) — ROUTE (split verdict)

- Gainers/losers/most-active are DONE via `digifetch_screener`
  (`GET /market/screener?category=gainers|losers|most-active&count&mode`,
  `data.ts:211-225`, categories `types.ts:1326`).
- Pre-market / after-hours / gaps: same route with session categories
  `premarket|afterhours|gaps` + `side=up|down|active`
  (`CloudSessionMoversCategory/Side`, `src/api-client/market-movers.ts:1-60`;
  `isSessionMoversCategory` gates the `side` param, `data.ts:220-224`).
  Shape: per-item price/change/ref-close/session volume/rel-volume/
  gap%/VWAP/catalysts (halt/filing/news), phase + as-of
  (`market-movers.ts:18-54`).
- Trending: NOT a Cloud route — Yahoo venue-direct
  `GET /v1/finance/trending/US` → symbols, hydrated with quotes
  (`fetchTrending`/`hydrateTrending`,
  `src/plugins/builtin/market-movers/screener.ts:439-451`,
  `client.ts:36-75`).
- Verdict: session movers → Cloud tool; trending → venue-direct
  (Yahoo precedent, same posture as the earnings calendar). Entitlement
  guess: `session` for the Cloud leg. Live: unverified.

### SUB — Substack — venue-DIRECT (own-account auth, fail-soft)

- No Gloom Cloud route: the plugin talks to `https://substack.com` directly
  (`SUBSTACK_ORIGIN`, `gloom-substack/api/store.ts:7`).
- Auth mechanism (own-account sign-in): magic email link or 6-digit OTP code
  (`gloom-substack/login-view.tsx:43-66`) → follows redirects harvesting
  `substack.sid` (+ `substack.lli`) cookies into `SubstackAuthState`
  (`gloom-substack/api/auth.ts:82-119,132-183`), persisted by the host
  (`api/store.ts:56-75`).
- Every data loader (`loadSubstackHome`, publication feed, article detail)
  calls `requireAuth()` first (`gloom-substack/api/loaders.ts:24-160`).
- Fail-soft: unauthenticated renders the login view, never an error
  (`gloom-substack/pane.tsx:70-102`); an expired session raises
  `SubstackAuthError`, which clears stored auth and drops back to login
  (`pane.tsx:88-101`). A tool without stored auth must return
  `auth_required` + login instructions, not fail.
- Verdict: direct-to-venue reader (personal session cookie; ToS grey area —
  same bucket as HN/fear-greed/market-halts). Live: unverified.

### IPO-overlap — Cloud-overlap question: YES → Cloud tool

- A `/cloud/*` IPO route EXISTS: `GET /cloud/ipo/calendar[?...]`
  (`CloudDataApi.getCloudIpoCalendar`, `src/api-client/data.ts:408-416`).
- The builtin IPO pane reads it (cached 15m, 7d expiry, "same payload for
  every account", `src/plugins/builtin/ipo-calendar/client.ts:1-24`); the
  route docstring states "Public, so it works signed out"
  (`src/api-client/ipo.ts:1-5`).
- Params: status/region/type/date filters (`IpoCalendarParams`, `ipo.ts`);
  shape: worldwide deals merged per venue — id/company/symbol/MIC/venue/
  dates/price range/offer size/status/filed→listed lifecycle/first-day
  open/close/return (`IpoDeal`, `ipo.ts:20-90`).
- (The external `gloom-ipo-calendar` plugin scrapes stockanalysis.com
  `__data.json` endpoints — `gloom-ipo-calendar/client.ts:8-9` — but that is
  NOT the builtin pane's path; the Cloud route answers the overlap question.)
- Verdict: Cloud tool, entitlement `open`. Live: unverified.

## Controller extras

### FRED series ids (money-market defaults + VIX legs)

From `docs/research-data.md:191-193` (BTMM board) with code corroboration:

- SOFR → `SOFR` (daily; with EFFR, IORB, OBFR as the daily-rates group).
- EFFR → `EFFR` (also the `fed-funds` default stat,
  `src/plugins/builtin/econ-statistics/stats.ts:387`).
- Reserves/liquidity → `WRESBAL` (weekly average ending Wednesday — not a
  Wednesday close), alongside `WALCL`, `WDTGAL` (Wednesday levels),
  `RRPONTSYD` (daily ON RRP); net liquidity = `WALCL - WDTGAL - RRPONTSYD`.
  (`WTREGEN` explicitly NOT used.) Bill tenors: `DTB4WK`, `DTB3`, `DTB6`,
  `DTB1YR` (discount basis).
- VIX legs: near = `VIXCLS` (FRED 30D), far = `VXVCLS` (FRED 3M, labeled
  "VIX 3M") — `VOLATILITY_SERIES`,
  `src/plugins/builtin/volatility/model.ts:4-7`. `VIX3M` as such is the
  Yahoo/CBOE index symbol `^VIX3M` used for the market-history curve leg
  (`model.ts:10-16`), NOT a FRED id. Tool defaults hitting FRED must use
  `VIXCLS`/`VXVCLS`.

### SUB auth + fail-soft (summary)

Own Substack account, magic-link/OTP → `substack.sid` cookie; all loaders
`requireAuth()`; no-auth = login view, expired = clear + login view. Tool
contract: `auth_required` without stored auth, never an exception-shaped
failure. See SUB verdict above.

### FLOW + IV-history gating (summary)

- FLOW: `pro` + `session`, no delayed tier; denials are typed
  (`auth_required`/`pro_required`); recorded-history REST is the toolable
  surface, fail closed. Evidence: `scanner/denied.tsx`, `scanner/feed.ts`,
  `data.ts:371-374`, `docs/research-data.md:436-445`.
- IV-history (`/cloud/iv/history`, `/cloud/iv/screen`, `/cloud/iv/surface*`):
  Cloud-stored (`session` guess); NO Pro-gate evidence found in source (no
  entitlement checks, no 402 handling, no plan hooks in the iv-history,
  vol-surface, realized-vol, or volatility plugins). Coverage is US option
  underlyings from Feb 2024. If the server gates harder, the tool surfaces
  the denial verbatim. Evidence: `iv-history/client.ts:78-96`,
  `docs/research-data.md:521`.

## Self-review

- [x] All 24 PROBE-matrix rows covered exactly once: TAS, QR, DDIS, OVDV,
      HIVG, HVG, HVT, VCA, EE, EMM, SIV, JOBS (research 12); SUB (news 1);
      MOST, CRYP, COT, HILO, FLOW, IPO (markets 6); CBR, CRD, CDX, SOVR
      (macro 4); INS (ownership 1). 12+1+6+4+1 = 24.
- [x] No live HTTP calls made; no operator approval recorded or assumed.
- [x] Every ROUTE row names method + path + params + entitlement guess +
      shape with file:line evidence; every NO-ROUTE row names its fallback
      (compose / OUT).
- [x] IPO Cloud-overlap answered (yes → Cloud tool); SUB states auth
      mechanism + fail-soft; FLOW + IV-history state gating.
- [x] FRED ids confirmed (SOFR/EFFR/WRESBAL; far leg VXVCLS, not VIX3M).
