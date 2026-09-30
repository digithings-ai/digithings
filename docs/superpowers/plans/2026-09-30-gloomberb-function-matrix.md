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
| TAS | Time and sales | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| QR | Quote recap | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| G | Custom chart | COMP | digifetch_custom_chart — explicit series list, aligned columns (Phase A) |
| CAT | Data catalog | DONE | digifetch_search |
| FAM | Financial analysis | DONE | digifetch_statements |
| DDIS | Debt maturities | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
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
| OVDV | Volatility surface | PROBE | Task 4 verdict incl. IV-history Pro gating (route + params + auth, or NO-ROUTE fallback) |
| HIVG | Implied volatility history | PROBE | Task 4 verdict incl. Pro gating (route + params + auth, or NO-ROUTE fallback) |
| HVG | Realized volatility | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| HVT | Volatility cone | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| VCA | Volatility rich/cheap | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| ANR | Analyst research | DONE | digifetch_analyst_research |
| EE | Earnings estimates | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| EMM | Estimate revisions | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| GUID | Company guidance | COMP | digifetch_company_guidance — best-effort quote harvesting over transcripts text, labeled as such, never advice (fallback: Task 4 PROBE verdict) |
| EVT | Corporate actions | DONE | digifetch_corporate_actions |
| DVD | Dividend yield | COMP | digifetch_dividend_yield — yield over corporate_actions + quote (Phase A) |
| SI | Short interest | DONE | digifetch_short_interest |
| SIV | Daily short volume | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| DIAG | Equity diagnostic | DONE | digifetch_equity_diagnostic |
| RISK | Risk factors | DONE | digifetch_risk_reports |
| EXEC | Executives | DONE | digifetch_proxy_statements |
| EK | 8-K filings | DONE | digifetch_filing_events |
| CALLS | Earnings calls | DONE | digifetch_transcripts |
| JOBS | Hiring | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
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
| SUB | Substack | PROBE | Task 4 verdict — auth-gated reader, fail-soft when no own-account sign-in |
| TV | Live TV | OUT | Live video pane, no tool surface |
| HN | Hacker News | TOS | digifetch_hacker_news — public API reader, free, unattributed, per-row source URLs (Phase C) |

## Watch markets (20)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| MOST | Market movers | DONE + PROBE | Screener DONE via digifetch_screener; trending / pre-market / after-hours = Task 4 PROBE |
| WEI | World equity indices | COMP | Composition over digifetch_quotes_batch — index/ETF basket (Phase A) |
| BI | Sector performance | COMP | Composition over digifetch_quotes_batch — sector ETF basket (Phase A) |
| RRG | Relative rotation | COMP | Composition over digifetch_quotes_batch — strength vs benchmark with momentum trails (Phase A) |
| HM | Market heatmap | COMP | Composition over digifetch_quotes_batch — cap-sized treemap rows (Phase A) |
| FXC | FX cross rates | COMP | digifetch_fx_cross_rates — USD-pair matrix over exchange_rate (Phase A) |
| CRYP | Crypto board | PROBE | Task 4 verdict — coin list source (route + params + auth, or NO-ROUTE fallback) |
| FUT | Futures board | OUT | Yahoo continuous symbols, prior decision |
| CTM | Futures curve | OUT | Yahoo continuous symbols, prior decision |
| FNG | Fear and greed | TOS | digifetch_fear_greed — unofficial CNN read, ToS grey area, cross-check before citing (Phase C) |
| COT | CFTC positioning | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| VIX | VIX term structure | COMP | digifetch_vix_term_structure — FRED composition over econ_series, contango/inversion (Phase A) |
| VOLS | Cross-asset volatility | COMP | digifetch_vix_term_structure — cross-asset board over econ_series (Phase A) |
| HILO | New highs and lows | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| FLOW | Options flow | PROBE | Task 4 verdict incl. Pro gating (route + params + auth, or NO-ROUTE fallback) |
| HALT | Market halts | TOS | digifetch_market_halts — Nasdaq Trader, delayed, free, unattributed (Phase C) |
| IPO | IPO calendar | TOS | digifetch_ipo_calendar — Cloud-overlap check first (Task 4); direct if no Cloud route (Phase C) |
| MAP | World venue map | DONE | digifetch_venues |
| PM | Prediction markets | DONE | digifetch_prediction_markets (venue-direct precedent: provider_id="prediction-markets-venues", attributed=False, per-row venue URLs) |
| POLL | Polls | TOS | digifetch_polls — VoteHub data © VoteHub contributors, CC BY 4.0, per-row attribution (Phase C) |

## Macro and rates (14)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| ECO | Economic calendar | DONE | digifetch_econ_calendar |
| ECST | Economic statistics | DONE | digifetch_econ_series |
| CBR | Central bank rates | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| GC | Yield curve | DONE | digifetch_yield_curve |
| WIRP | US rate path | COMP | digifetch_rate_path — fed-prob ladder over existing ingest + kalshi/polymarket reads (Phase A) |
| CRD | Credit spreads | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| AUCT | Treasury auctions | TOS | digifetch_treasury_auctions — Treasury Fiscal Data, public, free, unattributed (Phase C) |
| BTMM | Money markets | COMP | digifetch_money_markets — SOFR/EFFR/reserves are FRED series via econ_series (Phase A) |
| CDS | Single-name CDS | DONE | digifetch_cds |
| CDX | Index CDS | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| SOVR | Sovereign CDS | PROBE | Task 4 verdict (route + params + auth, or NO-ROUTE fallback) |
| YAS | Bond calculator | CALC | digifetch_bond_calculator — price/yield, accrued, duration, convexity, DV01, no transport (Phase A) |
| VAL | Market valuation | COMP | digifetch_market_valuation — Shiller CAPE + econ ratios vs history zones (Phase A) |
| ERN | Earnings calendar | DONE | digifetch_earnings_calendar (Yahoo-backed, deliberately NOT attributed to Gloomberb) |

## Ownership and filings (5)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| SEC | SEC filings | DONE | digifetch_sec_filings |
| HDS | Holders | DONE | digifetch_holders |
| 13F | 13F funds | DONE | digifetch_13f_funds / digifetch_13f_holdings |
| INS | Insider transactions | PROBE | Task 4 verdict — Form 4 (route + params + auth, or NO-ROUTE fallback) |
| CG | Congress trades | DONE | digifetch_congress_trades |

## Run a workspace (12)

| Prefix | Docs title | Status | Mapped tool or reason |
| ------ | ---------- | ------ | --------------------- |
| PF | Portfolio | WRITE | digifetch_portfolio_view (read) + watchlist/portfolio add/remove — probe Cloud write API first; read-only if no write route (Phase D) |
| PORT | Portfolio analytics | WRITE | digifetch_portfolio_view (read) — probe Cloud write API first; read-only if no write route (Phase D) |
| KELLY | Position sizer | CALC | digifetch_kelly_sizer — Kelly fraction, no transport (Phase A) |
| AW | Add to watchlist | WRITE | digifetch_watchlist_add — session-gated, zero-HTTP auth_required without cookie (Phase D) |
| AP | Add to portfolio | WRITE | digifetch_portfolio_add — session-gated, zero-HTTP auth_required without cookie (Phase D) |
| RW | Remove from watchlist | WRITE | digifetch_watchlist_remove — session-gated, zero-HTTP auth_required without cookie (Phase D) |
| RP | Remove from portfolio | WRITE | digifetch_portfolio_remove — session-gated, zero-HTTP auth_required without cookie (Phase D) |
| ALRT | Price alerts | WRITE | digifetch_alert_list — session-gated (Phase D) |
| SA | Add alert | WRITE | digifetch_alert_add — session-gated, zero-HTTP auth_required without cookie (Phase D) |
| NOTE | Notes | WRITE | digifetch_note_add — session-gated (Phase D) |
| THESIS | Investment theses | WRITE | digifetch_thesis_add — read-only if no write route (Phase D) |
| VIEW | Custom view | WRITE | digifetch_view_add — spec JSON Kroner; read-only if no write route (Phase D) |

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
| BR | Brokers | GATE | digifetch_broker_positions — read-only positions/account sync, session-gated (Phase E) |
| IBKR | IBKR trading | GATE | digifetch_ibkr_preview_order (ticket, never executes) + digifetch_ibkr_execute_order (two-phase approval ticket, HMAC, single-use, 15-min TTL; disabled pending human gate review) (Phase E) |

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
