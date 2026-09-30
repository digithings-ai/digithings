# Gloomberb 130-Function Coverage Matrix

Snapshot source: https://gloom.sh/docs/functions — 130 functions, verified 2026-09-30.

This doc is the per-function status table every later task in the
2026-09-30 gloomberb full-function-coverage plan argues from. Each of the 130
command-bar prefixes carries exactly one status, plus the mapped digifetch tool
name (shipped or planned) or the reason it stays out of scope.

## Status key

DONE (shipped) · CALC (pure calculator, Phase A) · COMP (composition over tooled
routes, Phase A) · PROBE (needs endpoint probe, Phase B) · TOS (direct-to-venue
with caveats, Phase C) · WRITE (workspace write, Phase D) · GATE
(approval-gated, Phase E) · NATIVE (digiquant-native, no gloomberb tool) · OUT
(declared out-of-scope with reason).

## Definition of done

"Complete integration" = every function carries one of these statuses, each
with a tool or a written reason. OUT items are listed in ARCHITECTURE with
reasons, not silently dropped.

Global contract for every tool built from this matrix: it returns
`DigifetchEnvelope[T]` and never raises (typed `DigifetchError`); contract
violations are rejected as `invalid_input`, never clamped; venue-direct data
must NOT claim "Sourced from Gloomberb" and must NOT emit `term.gloom.sh`
links; the `GLOOMBERB_ENABLED` kill switch gates the whole family including
calculators and compositions.

## Research companies (45)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| DES | Security overview | DONE | digifetch_ticker_financials |
| QQ | Quote monitor | DONE | digifetch_quotes_batch |
| GP | Price chart | DONE | digifetch_price_history |
| GIP | Intraday chart | DONE | digifetch_price_history |
| TAS | Time and sales | DONE | digifetch_time_and_sales — trades half of the shared Cloud tape snapshot (Task 5, Task 4 ROUTE) |
| QR | Quote recap | DONE | digifetch_quote_recap — NBBO quotes half of the shared Cloud tape snapshot (Task 5, Task 4 ROUTE) |
| G | Custom chart | COMP | digifetch_custom_chart — explicit series list, aligned columns (Phase A) |
| CAT | Data catalog | DONE | digifetch_search |
| FAM | Financial analysis | DONE | digifetch_statements |
| DDIS | Debt maturities | DONE | digifetch_debt_maturities — US-GAAP debt facts over the Cloud route (Task 5, Task 4 ROUTE) |
| HP | Historical prices | DONE | digifetch_price_history |
| CMP | Compare performance | COMP | digifetch_compare_performance — rebased returns over price_history (Phase A) |
| GFM | Fundamental graph | COMP | digifetch_fundamental_graph — statement fields over ticker_financials (Phase A) |
| GE | Valuation graph | COMP | digifetch_valuation_graph — trailing multiples over ticker_financials (Phase A) |
| GR | Relationship graph | COMP | digifetch_relationship_graph — indexed prices, ratio, rolling correlation, beta (Phase A) |
| CORR | Correlation matrix | COMP | digifetch_correlation_matrix — date-aligned Pearson matrix over price_history (Phase A) |
| BT | Backtest | NATIVE | digiquant_run_backtest (no gloomberb tool) |
| RV | Relative valuation | COMP | digifetch_relative_valuation — peer table over ticker_financials (Phase A) |
| EQS | Equity screener | DONE | digifetch_screener |
| OMON | Options monitor | DONE | digifetch_options_chain |
| OVME | Options calculator | CALC | digifetch_options_calculator — Black-Scholes price / IV solve, no transport (Phase A) |
| OSA | Options scenario | CALC | digifetch_options_scenario — multi-leg valuation over options_chain rows (Phase A) |
| OVDV | Volatility surface | DONE | digifetch_iv_surface — dated stored close surfaces (Task 5, Task 4 ROUTE); a live surface composes over options_chain + yield_curve |
| HIVG | Implied volatility history | DONE | digifetch_iv_history — stored daily IV history (Task 5, Task 4 ROUTE); server denial surfaces verbatim, 402-ready Pro gate |
| HVG | Realized volatility | COMP | Compose over price_history (close-to-close/Parkinson/Garman-Klass/Rogers-Satchell/Yang-Zhang over 20/30-session windows) + options_chain for the current-ATM-IV overlay (Task 4 NO-ROUTE) |
| HVT | Volatility cone | COMP | Compose over price_history (seven-window realized-vol distributions) + options_chain for the current-ATM-IV overlay (Task 4 NO-ROUTE) |
| VCA | Volatility rich/cheap | DONE | digifetch_iv_screen — stored IV screen over bare US symbols (Task 5, Task 4 ROUTE) |
| ANR | Analyst research | DONE | digifetch_analyst_research |
| EE | Earnings estimates | COMP | Compose over corporate_actions + analyst_research + ticker_financials (Task 4 NO-ROUTE, no dedicated Cloud route) |
| EMM | Estimate revisions | DONE | digifetch_estimate_revisions — per-period revisions over the Cloud route (Task 5, Task 4 ROUTE) |
| GUID | Company guidance | COMP | digifetch_company_guidance — best-effort quote harvesting over transcripts text, labeled as such, never advice (fallback: Task 4 PROBE verdict) |
| EVT | Corporate actions | DONE | digifetch_corporate_actions |
| DVD | Dividend yield | COMP | digifetch_dividend_yield — yield over corporate_actions + quote (Phase A) |
| SI | Short interest | DONE | digifetch_short_interest |
| SIV | Daily short volume | DONE | digifetch_short_volume — FINRA daily rows over the Cloud route (Task 5, Task 4 ROUTE) |
| DIAG | Equity diagnostic | DONE | digifetch_equity_diagnostic |
| RISK | Risk factors | DONE | digifetch_risk_reports |
| EXEC | Executives | DONE | digifetch_proxy_statements |
| EK | 8-K filings | DONE | digifetch_filing_events |
| CALLS | Earnings calls | DONE | digifetch_transcripts |
| JOBS | Hiring | DONE | digifetch_hiring — summary / postings / movers over the Cloud routes (Task 5, Task 4 ROUTE) |
| SRCH | Research search | DONE | digifetch_research_search |
| AI | AI screener | OUT | BYOK key, no data endpoint |
| AGENT | AI agent | OUT | BYOK key, no data endpoint |
| ASKG | Ask Gloom | OUT | Cloud AI chat, no data endpoint |

## Follow the news (9)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| TOP | Top news | DONE | digifetch_news (top feed) |
| N | News feed | DONE | digifetch_news (latest feed) |
| CN | Ticker news | DONE | digifetch_news (ticker feed) |
| NI | Sector news | DONE | digifetch_news (sector feed) |
| FIRST | Breaking news | DONE | digifetch_news (breaking feed) |
| TWIT | X feed | DONE | digifetch_ticker_tweets / digifetch_tweet_search |
| SUB | Substack | TOS | digifetch_substack — own-account venue-direct reader (SUBSTACK_SESSION_COOKIE), fail-soft auth_required without stored auth (Task 5, Task 4 venue-DIRECT) |
| TV | Live TV | OUT | Live video pane, no tool surface |
| HN | Hacker News | DONE | digifetch_hacker_news — public API reader, free, unattributed, per-row source URLs (Task 6) |

## Watch markets (20)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| MOST | Market movers | DONE | digifetch_screener (gainers/losers/most-active) + digifetch_session_movers (premarket/afterhours/gaps Cloud categories) + digifetch_trending (Yahoo venue-direct, unattributed) (Task 5, Task 4 split verdict) |
| WEI | World equity indices | COMP | Composition over digifetch_quotes_batch — index/ETF basket (Phase A) |
| BI | Sector performance | COMP | Composition over digifetch_quotes_batch — sector ETF basket (Phase A) |
| RRG | Relative rotation | COMP | Composition over digifetch_quotes_batch — strength vs benchmark with momentum trails (Phase A) |
| HM | Market heatmap | COMP | Composition over digifetch_quotes_batch — cap-sized treemap rows (Phase A) |
| FXC | FX cross rates | COMP | digifetch_fx_cross_rates — USD-pair matrix over exchange_rate (Phase A) |
| CRYP | Crypto board | DONE | digifetch_crypto_markets — up-to-100-coin board over the Cloud route (Task 5, Task 4 ROUTE) |
| FUT | Futures board | OUT | Yahoo continuous symbols, prior decision |
| CTM | Futures curve | OUT | Yahoo continuous symbols, prior decision |
| FNG | Fear and greed | DONE | digifetch_fear_greed — unofficial CNN read, ToS grey area, cross-check before citing (Task 6) |
| COT | CFTC positioning | DONE | digifetch_cot — board or one contract over the Cloud routes (Task 5, Task 4 ROUTE) |
| VIX | VIX term structure | COMP | digifetch_vix_term_structure — FRED composition over econ_series, contango/inversion (Phase A; far-leg default VXVCLS per Task 5 controller ruling — VIX3M is the ^VIX3M index symbol, not a FRED id) |
| VOLS | Cross-asset volatility | COMP | digifetch_vix_term_structure — cross-asset board over econ_series (Phase A) |
| HILO | New highs and lows | OUT | Socket-only streaming scanner, no REST equivalent and no tool-shaped equivalent; 52-week extremes already in quotes/screener (Task 4 NO-ROUTE → OUT) |
| FLOW | Options flow | DONE | digifetch_options_flow — recorded history route, Pro-gated, fails closed on denial (Task 5, Task 4 ROUTE) |
| HALT | Market halts | DONE | digifetch_market_halts — Nasdaq Trader, delayed, free, unattributed (Task 6) |
| IPO | IPO calendar | DONE | digifetch_ipo_calendar — Cloud-overlap confirmed: public Cloud route, anonymous (Task 5, Task 4 Cloud-overlap YES) |
| MAP | World venue map | DONE | digifetch_venues |
| PM | Prediction markets | DONE | digifetch_prediction_markets (venue-direct precedent: provider_id="prediction-markets-venues", attributed=False, per-row venue URLs) |
| POLL | Polls | DONE | digifetch_polls — VoteHub data © VoteHub contributors, CC BY 4.0, per-row attribution (Task 6) |

## Macro and rates (14)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| ECO | Economic calendar | DONE | digifetch_econ_calendar |
| ECST | Economic statistics | DONE | digifetch_econ_series |
| CBR | Central bank rates | DONE | digifetch_central_bank_rates — policy-rate board over the Cloud route (Task 5, Task 4 ROUTE) |
| GC | Yield curve | DONE | digifetch_yield_curve |
| WIRP | US rate path | COMP | digifetch_rate_path — fed-prob ladder over existing ingest + kalshi/polymarket reads (Phase A) |
| CRD | Credit spreads | COMP | Compose over econ_series via the Cloud FRED proxy — the six board ids (BAMLC0A0CM / BAMLC0A1CAAA / BAMLC0A2CAA / BAMLC0A3CA / BAMLC0A4CBBB / BAMLH0A0HYM2); no /cloud/credit spreads route (Task 4 compose verdict) |
| AUCT | Treasury auctions | DONE | digifetch_treasury_auctions — Treasury Fiscal Data, public, free, unattributed (Task 6) |
| BTMM | Money markets | COMP | digifetch_money_markets — SOFR/EFFR/reserves are FRED series via econ_series (Phase A) |
| CDS | Single-name CDS | DONE | digifetch_cds |
| CDX | Index CDS | DONE | digifetch_cdx — 5Y on-the-run board over the Cloud route (Task 5, Task 4 ROUTE) |
| SOVR | Sovereign CDS | DONE | digifetch_sovereign_cds — per-sovereign 5Y board over the Cloud route (Task 5, Task 4 ROUTE) |
| YAS | Bond calculator | CALC | digifetch_bond_calculator — price/yield, accrued, duration, convexity, DV01, no transport (Phase A) |
| VAL | Market valuation | COMP | digifetch_market_valuation — Shiller CAPE + econ ratios vs history zones (Phase A) |
| ERN | Earnings calendar | DONE | digifetch_earnings_calendar (Yahoo-backed, deliberately NOT attributed to Gloomberb) |

## Ownership and filings (5)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| SEC | SEC filings | DONE | digifetch_sec_filings |
| HDS | Holders | DONE | digifetch_holders |
| 13F | 13F funds | DONE | digifetch_13f_funds / digifetch_13f_holdings |
| INS | Insider transactions | COMP | Compose over sec_filings filtered to Form 4/4-A + filing content (parsed form4 block) (Task 4 NO-ROUTE) |
| CG | Congress trades | DONE | digifetch_congress_trades |

## Run a workspace (12)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| PF | Portfolio | WRITE | digifetch_portfolio_view (read) + watchlist/portfolio add/remove — Task 7 verdict: no personal Cloud write route verified (source probe 2026-09-30: team-scoped account APIs only, Live unverified) → session-gated, read-only posture, zero HTTP (Phase D) |
| PORT | Portfolio analytics | WRITE | digifetch_portfolio_view (read) — same Task 7 verdict as PF: read-only (Phase D) |
| KELLY | Position sizer | CALC | digifetch_kelly_sizer — Kelly fraction, no transport (Phase A) |
| AW | Add to watchlist | WRITE | digifetch_watchlist_add — session-gated, zero-HTTP auth_required without cookie; read-only per Task 7 verdict (Phase D) |
| AP | Add to portfolio | WRITE | digifetch_portfolio_add — session-gated, zero-HTTP auth_required without cookie; read-only per Task 7 verdict (Phase D) |
| RW | Remove from watchlist | WRITE | digifetch_watchlist_remove — session-gated, zero-HTTP auth_required without cookie; read-only per Task 7 verdict (Phase D) |
| RP | Remove from portfolio | WRITE | digifetch_portfolio_remove — session-gated, zero-HTTP auth_required without cookie; read-only per Task 7 verdict (Phase D) |
| ALRT | Price alerts | WRITE | digifetch_alert_list — session-gated (only a mobile history read exists upstream); read-only per Task 7 verdict (Phase D) |
| SA | Add alert | WRITE | digifetch_alert_add — session-gated, zero-HTTP auth_required without cookie; read-only per Task 7 verdict (Phase D) |
| NOTE | Notes | WRITE | digifetch_note_add — session-gated (upstream `/notes` is revision/team-scoped account API); read-only per Task 7 verdict (Phase D) |
| THESIS | Investment theses | WRITE | digifetch_thesis_add — read-only: upstream `/theses` is a team-scoped account API, no personal write route (Phase D) |
| VIEW | Custom view | WRITE | digifetch_view_add — spec JSON Kroner; read-only: upstream `/views` is a team-view account API, no personal write route (Phase D) |

## Cloud and brokers (9)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| CHAT | Chat | OUT | Account surface, no data API |
| DM | Direct messages | OUT | Account surface, no data API |
| TEAM | Teams | OUT | Account surface, no data API |
| FOCUS | Team focus | OUT | Account surface, no data API |
| TBO | TheBuildout | OUT | Account surface, no data API |
| ACM | Account management | OUT | Account surface, no data API |
| UPGRADE | Upgrade to Pro | OUT | Account surface, no data API |
| BR | Brokers | GATE | digifetch_broker_positions — read-only positions/account sync, session-gated; no fixed Cloud route verified (generic `/brokers/{broker}` session proxy only) → read-only posture, zero HTTP (Phase E) |
| IBKR | IBKR trading | GATE | digifetch_ibkr_preview_order (ticket, never executes) + digifetch_ibkr_execute_order (two-phase approval ticket, HMAC, single-use, 15-min TTL; DISABLED pending human gate review — upstream_error with zero brokerage traffic; dry-run returns the would-be request) — upstream orders go through the local gateway, not Cloud REST (Phase E) |

## Layouts and settings (16)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| GL | Tidy windows | OUT | App chrome, no API surface |
| LAY | Layouts | OUT | App chrome, no API surface |
| LMA | Layout actions | OUT | App chrome, no API surface |
| WIN | Window mode | OUT | App chrome, no API surface |
| PS | Pane settings | OUT | App chrome, no API surface |
| PL | Plugins | OUT | App chrome, no API surface |
| TH | Theme | OUT | App chrome, no API surface |
| LANG | Language | OUT | App chrome, no API surface |
| FONT | Font size | OUT | App chrome, no API surface |
| SB | Status bar | OUT | App chrome, no API surface |
| VF | Value flashing | OUT | App chrome, no API surface |
| CR | Chart renderer | OUT | App chrome, no API surface |
| CONN | Connections | OUT | App chrome, no API surface |
| CHG | Changelog | OUT | App chrome, no API surface |
| HELP | Help | OUT | App chrome, no API surface |
| FB | Send feedback | OUT | App chrome, no API surface |

## Counts

45 research + 9 news + 20 markets + 14 macro + 5 ownership + 12 workspace +
9 cloud/brokers + 16 layouts/settings = 130.
