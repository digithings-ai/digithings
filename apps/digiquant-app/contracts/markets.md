# Contract fragment: markets (market tools, FX desk, rates desk)

All routes: envelope `{ data, as_of, provenance }` per CONTRACT.md section 1. Types: `lib/api-markets.ts`. Null means "not available": render an em dash, never zero or a carried-forward value. Note: `/v1/tables/:t` returns a bare row array (no envelope), so blocks that the BLOCKS.md marks "table" use dedicated enveloped routes below (the worker may implement them by reading those tables).

## Market tools

| route | query | data | source |
|---|---|---|---|
| `GET /markets/quotes` | `symbols=A,B,C` (required, comma list, max ~50) | `{ quotes: [{ symbol, name?, last\|null, net?, pct?, bid?, ask?, volume?, time? }] }`; one entry per requested symbol, `last=null` when no print | upstream `/v1/market/tickers` (twelve-x) |
| `GET /markets/bars` | `symbol`, `interval` (1m..1W), `indicators=ema20,rsi14` | `{ symbol, interval, venue?, bars: [{ t, o, h, l, c, v? }], indicators?: { ema20: (n\|null)[], rsi14: (n\|null)[] } }`, chronological, indicator arrays aligned to bars | market bars API; indicators computed server-side |
| `GET /tape` | `limit?` | `{ items: [{ time\|null, headline, tag?\|null }] }`, newest first | `run_event_trace` / `decision_log` |
| `GET /charts/series` | none | `{ defaults?: { symbol, range, series }, series: [{ id, label, source?, status? }] }` | static registry |

Blocks sharing a route: `mk-ticker-strip`, `mk-quote-board`, `mk-fx-crosses` (quotes with different `symbols`); `mk-price-pane`, `mk-volume-pane`, `mk-rsi-pane`, `mk-ohlc-readout` (bars; one fetch is shared per identical URL).

## FX desk (all new)

| route | data | source |
|---|---|---|
| `GET /fx/summary` | `{ desk?, run_date, posture?, pairs?: {count, note?}, ideas?: {count, note?}, paper_exposure?: {gross_usd, venue?}, session?: {name, note?}, research_flags?: {count}, read?: {lead, body?}, changes?: string[] }` | `fx_trade_ideas_snapshot` + run metadata |
| `GET /fx/pairs` | `{ pairs: [{ pair, bid, offer, day_pct, session?, path?: (n\|null)[], bias?, status? }] }` | FX board snapshot (twelve-x) |
| `GET /fx/pairs/:pair/path` | `{ pair, session?, points: [{ t, v\|null }], note? }` | FX board intraday path |
| `GET /fx/ideas` | `{ ideas: [{ rank\|null, pair, bias?, horizon?, invalidation?\|null, status?, levels?, thread? }] }`; status values seen: carried, missing_rates, dropped | `fx_trade_ideas_snapshot` |
| `GET /fx/ideas/:pair` | `{ pair, rank?, headline?, rationale?, bias?, horizon?, status?, invalidation?: {value\|null, provenance?}, entry?: {low\|null, high\|null, provenance?}, target?: {value\|null, provenance?}, catalyst?, evidence_note? }` | `fx_trade_ideas_snapshot` |
| `GET /fx/levels` | `{ levels: [{ pair, mark\|null, level\|null, role?, pips?\|null, provenance?, flag? }] }`; absent level is null, not 0 | idea levels + board mid |
| `GET /fx/flags/:pair` | `{ pair, flagged: boolean, level?, text?, scope_note? }`; display-only, never steers generation | research flag table |
| `GET /fx/paper-exposure` | `{ venue?, gross_usd\|null, note?, lines: [{ pair, side\|null, notional_usd\|null, venue? }] }` | paper positions (venue PAPER_INTERNAL when no broker) |
| `GET /fx/sessions` | `{ sessions: [{ session, state\|null, note?, active? }] }` | clock + board |
| `GET /fx/directives` | `{ allow_pairs: string[], deny_pairs: string[], risk_style\|null, risk_style_options?: string[], ignore_sources: string[], writable?: boolean, note? }` | desk settings |
| `PUT /fx/directives` | body `{ allow_pairs, deny_pairs, risk_style\|null, ignore_sources }` (all arrays required; pairs are 6 uppercase letters); returns the stored directives in the envelope. 422 `invalid_body` for a bad body; the UI shows the status text, never a fake success. If the writer contract is not wired return `writable: false` on GET (UI goes read-only) | desk settings |

Path params (`:pair`) are URL-encoded. Block components `FxPairPathBlock`, `FxIdeaDetailBlock`, `FxFlagsBlock` take a `pair` prop; the registry seeds `FX_DEFAULT_PAIR` ('USDJPY').

## Rates desk (all new, except theses)

| route | data | source |
|---|---|---|
| `GET /rates/summary` | `{ desk?, run_date, posture?, watchlist?: {names, marks_available}, theses?: {active: string[], watch: string[]}, last_run?: {date, note?}, budget?: {spent_usd, cap_usd}, read?: {lead, body?}, signals?: [{id, name, state, note?}], risks?: string[] }` | rates desk run + `theses` |
| `GET /rates/watchlist` | `{ names: [{ ticker, name?, mark\|null, day_pct?, mark_source?, thesis_id? }] }`; `mark=null` renders unavailable | rates watchlist + marks |
| `GET /rates/curve` | `{ curve: [{ tenor, yield_pct\|null, day_change?\|null }], spreads?: [{ label, bp\|null, day_bp?\|null }] }` | `macro_series_observations` |
| `GET /rates/theses` | `Theses` shape (`{ theses: [{ id, name, state, vehicles, evidence, kill_condition, note }], counts: { active, watch, exited, by_status } }`); `state` is the row's own `theses.status` lowercased, or `—` when NULL. `evidence` and `kill_condition` are **rendered prose**, not the raw jsonb: `validation_criteria` and `invalidation_criteria` (else `invalidation`) are flattened to a `; `-joined, de-duplicated, 400-character-capped string. `note` reads `notes`. `counts.by_status` holds every `chk_theses_status` token plus `unknown` and is the full partition; `active`/`watch`/`exited` are rollups over it (`watch` = monitoring + challenged, `exited` = closed + invalidated), so a book whose rows are all `paused` or `new` prints three zeros above a full table — read `by_status` for the truth. **No desk filter** — core `theses` has no `desk` column, so this is every house thesis, not only rates. | `theses` + `thesis_vehicles` |
