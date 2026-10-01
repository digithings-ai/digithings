# digiquant-app — block library and API map

Source: the :3920 canvas mock (38 pages), mapped by `dq-block-inventory` (114 raw regions → ~40 blocks + primitives below).
Rule: **one block = one primitive composition + one API route.** Primitives carry all borders, spacing, fonts and states; blocks only choose fields.
Route status: **exists** (CONTRACT §6) · **extend** (add fields to an existing route) · **table** (generic `/v1/tables/:t` can serve) · **new**.

## 1. Primitives (the standard library — build once, reuse everywhere)

| primitive | covers (mock class) | status |
|---|---|---|
| `Window` | `.sec` + eyebrow bar (`NN / label`, right slot, hairline frame, body scrolls) | done |
| `DataTable` | `.tw` — sticky th, `.num`, row variants `sel/total/grp`, inline weight bar, wrap/clamp for long text | partial |
| `KpiGrid` | `.kpis/.kpi` (label / value / sub, tones) | done |
| `Badge` / `Chip` | `.badge` ok/wip/gap/unavailable/live/kind(OPEN·ADD·TRIM·EXIT)/state(active·watch·exited), `.chip` paper | todo |
| `Sparkline` / `LineChart` / `Candles` / `VolumePane` | `.pane` SVG idiom, last-price dot, axis labels | spark done |
| `MetaStrip` | `.meta` inline "Label **value**" pairs (band, run health, OHLC readout) | todo |
| `PageBand` | `.band` breadcrumb + h1 + lede + MetaStrip | todo |
| `Tabs` | `.tabs/.tab` (portfolio sub-tabs, timeframes, settings) | todo |
| `KvList` | `.kv` definition rows (position detail, overview, settings cards) | todo |
| `Prose` / `BulletList` | `.doc/.prose/.lead/.soft`, `ul.plain` | todo |
| `StateBlock` | `.empty` — empty / loading / error with why + next actions; one-line section variant | todo |
| `SoonBar` | `.soonbar` badge + text + actions | todo |
| `Button`, `Field`, `Select`, `Toggle`, `SecretField` | `.btn/.primary/.off`, form chrome, masked key | todo |
| `Stepper`, `FlowNode` | `.steps`, pipeline `.canvas/.node` | todo |
| Format helpers | `pct/px/signed` done; add `bp`, `pp`, U+2212 minus, `—` for null, never zero | partial |
| Shell | sidebar+pin, command line done; `TickerStrip`, `StatusChip`, `DeskPicker`, `Footer`, `ChatRail` todo | partial |

Robustness contract for every primitive: null → `—`; long text wraps or clamps (never widens its frame); numbers `tabular-nums`; own scroll, never page scroll; layout in `rem`/`%`, no fixed px widths, so browser zoom 50–200% stays contained.

## 2. Data blocks → routes

### Portfolio
| block | primitive | route | status | gap |
|---|---|---|---|---|
| book-kpis | KpiGrid | `/brief` + `/performance` | extend | 5-day return, max/current drawdown (+dates), positions open/unmarked, NAV USD |
| decision | Prose | `/brief` | extend | `data.decision {lead, body, run_date}` |
| risks | BulletList | `/brief` | extend | `data.risks: string[]` |
| signals | DataTable | `/v1/tables/theses` | table | add `GET /theses?needs_resolution=` |
| book (holdings) | DataTable (grp/total/bar) | `/allocations` | extend | name, sleeve, shares, value, day_return_pct, thesis_id, mark_source; `data.cash_value/book_value` |
| sleeves | DataTable + bar | `/allocations` | extend | `data.sleeves [{sleeve, names, weight_pct}]` |
| movers | DataTable | `/allocations` | extend | `?sort=day&limit=` |
| summary-strip | MetaStrip | per page route | extend | `summary {book_events, open_positions, reconciles}` etc. |
| ledger-fills | DataTable | `/ledger` | exists | |
| position-events | DataTable | `/ledger?ticker=` | exists | |
| cash-ledger | DataTable | `/ledger/cash` | new | |
| performance-periods / prose | DataTable / Prose | `/performance` | exists | |
| nav-table / nav-chart | DataTable / LineChart | `/nav-series` + `/benchmarks` | exists | |
| drawdown | DataTable | `/performance` | extend | `drawdown {max, peak, trough, current}` |
| attribution-sleeve / name | DataTable | `/v1/tables/position_attribution` | table | add `GET /attribution?window=` |
| theses | DataTable (long text) | `/v1/tables/theses` + `thesis_vehicles` | table | add `GET /theses` joined, with counts |
| position-detail | KvList | `/allocations?ticker=` | extend | |
| symbol-closes | DataTable | `/benchmarks?tickers=` | exists | |
| ticker-dossier | composite | `/allocations`, `/theses`, `/benchmarks` | exists | |

### Market / tools
| block | route | status |
|---|---|---|
| ticker-strip (top bar) | `GET /markets/quotes?symbols=` | new (upstream `/v1/market/tickers`) |
| quote-board, fx-crosses | `GET /markets/quotes` | new |
| price-pane, volume-pane, rsi-pane, ohlc-readout | `GET /markets/bars?symbol=&interval=&indicators=` | new |
| news-tape | `/v1/tables/run_event_trace` or `decision_log`; later `GET /tape` | table |
| rates-curve | `/v1/tables/macro_series_observations` | table |
| chart-series-registry | `GET /charts/series` | new |

### Pipeline / strategies
| block | route | status |
|---|---|---|
| run-health | `/v1/tables/run_health` → `GET /pipeline/runs/:date/health` | table → new |
| pipeline-canvas | `GET /pipeline/runs/:date/graph` | new |
| node-document, narrative | `GET /pipeline/runs/:date/nodes/:n/document`, `/narrative` | new |
| call-trace, artifact-ledger | `GET /pipeline/runs/:date/trace`, `/artifacts` | new (tables meanwhile) |
| strategies-kpis / catalog / deployments / targets | `GET /strategies/summary`, `/strategies`, `/strategies/deployments`, `/strategies/targets` | new |
| strategy-overview / parameters / track-record / runs | `GET /strategies/:id`, `/parameters`, `/performance`, `/runs` | new |
| deploy-flow, deploy-draft, deploy-action | `GET /strategies/deploy-flow`, `/:id/deploy-draft`, `POST /strategies/:id/deployments` | new (action: not built) |

### Chat
| block | route | status |
|---|---|---|
| chat-sessions, thread, transcript, tool-call | `GET /chat/sessions`, `/chat/sessions/:id`, `/:id/messages` | new |
| chat-composer | `POST /chat/sessions/:id/messages` | new (write) |

### FX / rates desk
`GET /fx/summary`, `/fx/pairs`, `/fx/pairs/:pair/path`, `/fx/ideas`, `/fx/ideas/:pair`, `/fx/levels`, `/fx/flags/:pair`, `/fx/paper-exposure`, `/fx/sessions`, `GET/PUT /fx/directives`, `/rates/summary`, `/rates/watchlist` — all **new**; `rates-theses` = `/v1/tables/theses?desk=rates` (**table**).

### Settings / shell
`GET /settings/prefs` (+PUT), `/settings/desk`, `/settings/fx-feed`, `/settings/brokers` (+`POST …/connect`), `/settings/integrations`, `/settings/keys` (+POST mint / DELETE revoke), `GET /desks`, `/desks/:id/spine`, `/features` (soon-bar flags), `GET /pipeline/runs/latest` (status chip). Theme toggle = client only. All **new**.

## 3. Counts
Existing routes cover 8 blocks fully; ~14 more are `extend`/`table`; ~35 routes are **new** and need worker work (`apps/dashboard-api`). Until a route ships, its block shows the `StateBlock` "withheld" state — never invented data.

## 4. Build order
1. Primitives (section 1), each with a null/long-text/empty fixture, reviewed on `/blocks`.
2. Blocks on existing + extend routes (portfolio group).
3. Layout grid: place / rearrange / resize + zoom check.
4. Remaining groups, with their API routes added to the worker + `CONTRACT.md` as each lands.
