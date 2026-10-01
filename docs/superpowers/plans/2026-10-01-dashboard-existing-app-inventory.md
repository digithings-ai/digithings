# DigiQuant dashboard existing-app inventory (lane 1/3)

> **For agentic workers:** This file is an inspection record, not an implementation plan. Do not write React, HTML mockups, or visual polish from it. Later lanes own information architecture and craft. Lane 1 stops at inventory.

**Goal:** Record what the live digiquant dashboard (`apps/dashboard`, public base path `/dashboard`) actually ships today, mapped against the lab spine, so a ground-up rebuild can keep wired research and paper-book behavior and treat missing product surfaces as coming-soon.

**Architecture:** Static Next.js export. One root layout, one app frame (sidebar + main), client pages. Data is a Cloudflare Workers dashboard API plus Supabase Edge Functions for settings. twelve-x (FX Hub) and the digichat embed are separate backends. The browser does not call MCP.

**Tech Stack:** Next.js 15 static export (`output: 'export'`, `basePath: '/dashboard'`, `trailingSlash: true`), React client pages, `@digithings/ui`, Supabase Auth (flagged), Workers API, settings Edge Function, `@luxalgo/vela` on one spike route only.

**Scope of this file:** `apps/dashboard` and the operator product it serves at `digiquant.io/dashboard/`. Marketing showcase `apps/digiquant-web` is out of the product surface and is listed only so it is not mistaken for the dashboard.

**Out of scope:** UI code, HTML mockups, visual polish, live-trading paths, new dependencies.

## Global Constraints

Paste and honor on every later lane. These are product locks, not suggestions.

### Product split

- Dashboard = live product: chat strategy builder, strategies, trade journaling, digiquant tools, and solution integrations in-app.
- digiquant-web = showcase only. It is not the full tool surface.

### Every surface

1. Research + paper book first. No live-trading claims. No guaranteed-alpha claims.
2. Human gate before live. Paper is the default. Coming-soon is acceptable for live paths.
3. Job words only. No Olympus, Atlas, Hermes, or Kairos in UI labels.
4. digi* names stay lowercase in chrome. DigiQuant as a brand name is allowed.
5. LuxAlgo is the charting backbone. Do not add a competing chart stack.
6. The dashboard owns the tool surface. The marketing site only teases it.
7. Craft follows digiquant-web (finance-native ground-up information architecture). Do not re-skin the heavy shell.
8. Access-gated. This is not a public marketing page.
9. Never private-client names in chrome, copy, plans, or fixtures.

### Web UX (later lanes; recorded here so inventory does not invent a different shell)

- Sidebar = top-level only, literal labels, never icon-only: Chat / Strategies / Journal / Research|Portfolio|Signals / Tools|Integrations / Settings.
- Sticky in-page tab bar for within-subject sections. Reference: `packages/design/references/dashboard-subpage-chrome.md`.
- LuxAlgo and Gloomberb are embeds or destinations. Do not rebuild them as competitors.
- Settings taxonomy (SETTINGS-IA): Profile | Pipeline | Keys | Brokers | Notifications | Billing | About.
- Tier rule: omit tabs the plan cannot use. Never grey them and never show a lock tease.
- Observer and Brief: Notifications | Billing | About.
- Desk adds Brokers.
- Studio and above: full set.
- Deep links: `#hash` and `?tab=`. No free-form model-id picker in v0.
- Coming-soon: honest chip or empty state. Prefer omit from nav until the surface is demo-safe. If a row is listed, it is disabled plus one line of status. No fake tables or charts.
- Execution and live trading: coming-soon only.
- Craft: follow digiquant-web `:3910` (#4885), not the fat shell (#4896). Flat `--surface` and hair borders. Blur only on sticky chrome and overlays. Type toward Inter and JetBrains Mono.
- Parked #4885, #4892, and #4896 are reference only.
- No visual polish in this plan.

### Lab spine (cross-check target)

Must-haves to account for, at `apps/dashboard` with base path `/dashboard`:

Brief, Holdings, Theses, Tearsheet, Ledger, Attribution, Pipeline, House, Settings (Profile, Pipeline, Keys, Brokers, Notifications, Billing, About), Auth, optional Ticker.

Explicit flags:

- `/strategy` is a theses redirect, not a strategy builder.
- `/why` is legacy beside Pipeline.
- Coming-soon gaps relative to the product lock: strategy builder, trade journaling, live brokers, digichat as a first-class product surface.

---

## 1. Where the app lives

| Fact | Value |
|------|--------|
| Workspace | `apps/dashboard` (npm package `dashboard`) |
| Public base path | `/dashboard` (`apps/dashboard/next.config.mjs`) |
| Export | `output: 'export'`, `trailingSlash: true`, images unoptimized |
| Production host | `digiquant.io/dashboard/` |
| Root layout | `apps/dashboard/app/layout.tsx` — theme boot script, Geist Mono variable, `AuthProvider` → `AuthGate`. No sidebar here. |
| Shell | `apps/dashboard/components/app-frame.tsx` — sidebar, mobile app bar, command palette, digichat popup, DB-down gate, FX-Hub-only guard. Mounted from `lib/auth-gate.tsx` for signed-in (or auth-off) routes. |
| Auth routes | `/login`, `/signup`, `/auth/callback` render without the app frame. |
| Primary nav source | `apps/dashboard/lib/nav.ts` `NAV` — consumed by desktop sidebar and mobile app bar. |
| In-page section chrome | `apps/dashboard/components/subpage-tab-bar.tsx` (`SubpageStickyTabBar`). Width constant `SUBPAGE_MAX` in `components/layout-constants.ts`. |

There is no `apps/dashboard/ARCHITECTURE.md`. Behavior notes live in `apps/dashboard/README.md`, `apps/dashboard/AUTH.md`, `apps/dashboard/lib/CHARTS.md`, and `apps/dashboard/lib/TABLES.md`.

`apps/digiquant-web` (`/`, `/strategies`, `/strategies/[id]`, `/pipeline`, `/subsystems/[id]`, `/changelog`, `/contact`) is the public showcase. Its strategy library renders published Nautilus tearsheets for marketing. It is not the operator tool surface and must not be rebuilt as one.

---

## 2. Lab spine cross-check

Paths below are app-relative. The browser path prefixes `/dashboard`.

| Lab must-have | App path | File | Verdict |
|---------------|----------|------|---------|
| Brief | `/` | `app/page.tsx` → `components/today/daily-brief-workspace.tsx` | **Present.** Sidebar label "Brief". Wired to Workers API portfolio/brief/performance plus run-health. |
| Holdings | `/portfolio` (default tab) | `app/portfolio/page.tsx` → `PortfolioShellInner` → `AllocationsTab` | **Present.** Section nav label "Holdings". |
| Theses | `/portfolio?tab=theses` | same shell → `ThesesTab` | **Present.** `/portfolio/theses` redirects here (preserves `date`). Thesis detail is `?thesis=<id>` on that query, not a dynamic segment. |
| Tearsheet | `/portfolio/performance` | `app/portfolio/performance/page.tsx` → `PerformanceTearsheetView` | **Present.** Entitled `house_weights_nav` (Brief+). |
| Ledger | `/portfolio/ledger` | `app/portfolio/ledger/page.tsx` | **Present.** Same entitlement. Position events, not a private accounting base table. |
| Attribution | `/portfolio/attribution` | `app/portfolio/attribution/page.tsx` → `AttributionWorkspace` | **Present.** Same entitlement. Views: Decision effectiveness, Book attribution, Audit. |
| Pipeline | `/pipeline` | `app/pipeline/page.tsx` → `PipelineClient` | **Present.** Glass-box topology, artifact ledger, call trace. |
| House | `/house?tab=corpus\|book\|profile` | `app/house/page.tsx` | **Present, not in the sidebar.** Command palette only. Read-only Corpus \| Book \| Profile. Profile pins are declared chrome, not editable Settings. |
| Settings Profile | `/settings#profile` or `?tab=profile` | `app/settings/page.tsx` | **Present, Studio+ only.** Omitted below Studio. |
| Settings Pipeline | `/settings#pipeline` | same | **Present, Studio+ only.** |
| Settings Keys | `/settings#keys` | same | **Present, Studio+ only.** |
| Settings Brokers | `/settings#brokers` | same | **Present, Desk+.** Paper only. |
| Settings Notifications | `/settings#notifications` | same | **Present, every plan.** |
| Settings Billing | `/settings#billing` or `?tab=billing` / `?checkout=success\|cancel` | same | **Present, every plan.** |
| Settings About | `/settings#about` | same | **Present, every plan.** Default when the requested tab is gated. |
| Auth | `/login`, `/signup`, `/auth/callback` | `app/login/page.tsx`, `app/signup/page.tsx`, `app/auth/callback/page.tsx` | **Present.** Supabase Google + GitHub PKCE and email. Flag `NEXT_PUBLIC_DASHBOARD_AUTH=1`. Flag off keeps the anon client. |
| Ticker (optional) | `/portfolio/tickers?ticker=` | `app/portfolio/tickers/page.tsx` | **Present.** Static page, query param, not `[ticker]`. |

### Flags the lab called out

| Path | What it is | What it is not |
|------|------------|----------------|
| `/strategy` | `app/strategy/page.tsx` → `StrategyToAnalysisRedirectPage`. With `?thesis=` it goes to `thesisDetailHref`. Otherwise `/portfolio?tab=theses`. | Not a strategy builder, not a strategy library, not chat. |
| `/why` | `app/why/page.tsx` still mounts `WhyClient` ("The read" \| "Deliberations"). Not in `NAV`. Sidebar highlights Pipeline when the path matches `/why` because Pipeline absorbed the old Why destination, but the page itself still renders. | Not the Pipeline glass-box. Not deleted. Treat as legacy beside Pipeline. |

`/research` and `/library` are named `*ToWhy*` in `components/legacy-spa-redirect.tsx` but their `router.replace` target is Pipeline (`buildPipelineHref`), not `/why`.

### Coming-soon gaps (product lock vs this tree)

| Gap | Current code | Honest status for a rebuild |
|-----|--------------|-----------------------------|
| Strategy builder | No route, no component, no MCP tool call from the dashboard. `/strategy` redirects to theses. | **Missing.** Coming-soon until a demo-safe builder exists. Do not pretend theses are the builder. |
| Trade journaling | No route, no journal model, no nav item. Ledger is pipeline position events (OPEN / ADD / EXIT / TRIM), not a user trade journal. | **Missing.** |
| Live brokers | Brokers tab hard-codes `env: 'paper'` in `lib/settings-api.ts` (`connectBrokerApiKey`, `connectBrokerOAuth`). UI copy is "Connect Alpaca (paper)" and "Save API key (paper)". IBKR is labeled beta for paper/dev. No live-env control. | **Paper wired (Desk+). Live is coming-soon only.** |
| digichat | Not a route. `DigichatPopup` in the app frame iframes digichat `/embed?layout=embed` for Desk / Studio / Enterprise. Observer and Brief get an upgrade CTA and no iframe. Kill switch `NEXT_PUBLIC_DIGICHAT_POPUP=0`. | **Embed exists for entitled plans. Not a sidebar Chat destination and not a strategy builder.** Treat first-class Chat as coming-soon relative to the target spine. |

---

## 3. Full route tree

App-relative paths. Public URL is `/dashboard` + path + trailing slash.

### Live pages

| Path | Role | In sidebar `NAV`? |
|------|------|-------------------|
| `/` | Brief (daily decision workspace) | Yes — "Brief" |
| `/portfolio` | Holdings, or Theses when `?tab=theses` | Yes — "Portfolio" (holdings and theses share this item) |
| `/portfolio/performance` | Tearsheet | No (section tab) |
| `/portfolio/ledger` | Ledger | No (section tab) |
| `/portfolio/attribution` | Attribution | No (section tab) |
| `/portfolio/tickers` | Ticker dossier `?ticker=` | No (links and command palette) |
| `/pipeline` | Pipeline glass-box. Deep link `?date=&stage=&node=` | Yes — "Pipeline" |
| `/why` | Legacy reasoning workspace `?why=read\|deliberations` | No |
| `/house` | House identity `?tab=corpus\|book\|profile` | No |
| `/settings` | Settings tabs | Footer control, not a `NAV` row |
| `/settings/brokers/callback` | Alpaca OAuth return. Posts paper connect, then back to Brokers | No |
| `/twelve-x` | FX Hub client product. Tabs below. Gated by `fx_hub` | Yes — "FX Hub", only when `canFxHub` |
| `/research/vela-spike` | LuxAlgo Vela spike. `?symbol=` (default `BTC-USD`), `?timeframe=` (default `1d`) | No |
| `/login`, `/signup`, `/auth/callback` | Auth, no app frame | No |

### Client redirects (no content of their own)

Implemented in `components/legacy-spa-redirect.tsx` unless noted.

| Path | Lands on |
|------|----------|
| `/strategy` | `/portfolio?tab=theses`, or thesis detail when `?thesis=` is set |
| `/why` | **Does not redirect.** Still a page. See flag above. |
| `/research` | Pipeline, preserving `date` |
| `/research/vela-spike` | **Does not redirect.** Child route stays. |
| `/library` | Pipeline node, preserving `date` and `docKey` |
| `/observability` | `/pipeline` (query string kept) |
| `/architecture` | `/pipeline` (query string kept) |
| `/performance` | `/portfolio/performance` |
| `/portfolio/period` | `/portfolio/performance` |
| `/portfolio/theses` | `/portfolio?tab=theses` (preserves `date`) |
| `/system` | `/pipeline` (`app/system/page.tsx`, local redirect) |

Path-form thesis URLs (`/portfolio/theses/<id>`) are not served. Static export 404s them. In-app links use `thesisDetailHref()`.

### FX Hub tabs (`/twelve-x`)

From `TWELVE_X_TABS` in `components/twelve-x/TwelveXClient.tsx`:

Today, Consensus, Trades, Matrix, Events, How it works.

Brief, idea, and track-record panels are drill-ins (`?brief=`, `?tab=trades`, `?tab=matrix`), not extra sidebar items. An FX-Hub-only invitee (product grant, free tier) sees only FX Hub. Brief, Portfolio, Pipeline, Gloomberb, and desk Settings are hidden. Settings becomes a sign-out / invite card (`FxHubAccount`).

### Portfolio section tabs

`components/portfolio/PortfolioSectionNav.tsx`:

| Label | Href |
|-------|------|
| Holdings | `/portfolio` |
| Theses | `/portfolio?tab=theses` |
| Tearsheet | `/portfolio/performance` |
| Ledger | `/portfolio/ledger` |
| Attribution | `/portfolio/attribution` |

`VALID_PORTFOLIO_TABS` on the shell page is holdings and theses only. Tearsheet, Ledger, and Attribution are separate routes that reuse the same bar.

### Pipeline stages (in-page, not routes)

`lib/pipeline-topology.ts`: Inputs (Preflight, Attention plan) → Research (Alt-data, Institutional, Macro, Asset-classes, Sectors) → Synthesis (Consolidate bias, Daily digest) → Selection (Thesis framing, Screener, Analysts, Deliberation, PM direction, Risk sizing) → Decision (Commit) → Learning (Beliefs fold).

Three inspection surfaces on the same page: topology, All artifacts, Call trace (`run_event_trace`). Inputs call rows are an admitted persistence gap. The UI says so.

### Why tabs (legacy page)

`lib/why-tabs.ts`: The read (`?why=read`), Deliberations (`?why=deliberations`). Documents archive was removed. Per-day documents live on Pipeline.

### House tabs

Corpus, Book, Profile. Book copy is "House ETF paper book" and "Paper book — no live-trading path". Not an editable settings surface.

### Shell chrome that is not a route

| Chrome | File | Behavior |
|--------|------|----------|
| Sidebar | `components/sidebar.tsx` | `NAV` plus external "Gloomberb Terminal" (`GLOOMBERB_TERMINAL_URL`). Collapses to a 72px rail; labels become `md:sr-only` with a tooltip. That is icon-only on desktop when collapsed. |
| Mobile app bar | `components/mobile-app-bar.tsx` | Same `NAV`. |
| Command palette | `components/command-palette.tsx` | ⌘K. Brief, Holdings, Theses, Tearsheet, Ledger, Attribution, House corpus, Pipeline, digest node, selection stage, FX Hub, Settings, theses, tickers, twelve-x drills. |
| digichat popup | `components/digichat-popup.tsx` | Bottom-right launcher. See coming-soon gap. |
| DB-down gate | `components/db-unavailable.tsx` | When `NEXT_PUBLIC_DASHBOARD_API_URL` is missing or the fetch fails, non-exempt routes swap to an unavailable card. Exempt prefixes in `DB_EXEMPT_PREFIXES`: `/system`, `/settings`, `/twelve-x`, `/architecture`, `/library`, `/observability`, `/performance`, `/research`, `/strategy`, `/portfolio/theses`, `/house`. |
| Page chrome comment in README | `app/layout.tsx` | README still describes a `.qn-page-chrome` crumb strip. The current root layout does not render that strip. The frame is sidebar + main. |

Sidebar `NAV` today (literal labels, with icons):

1. Brief → `/`
2. Portfolio → `/portfolio`
3. Pipeline → `/pipeline`
4. FX Hub → `/twelve-x` (product-gated)

Settings is a footer button (`components/sidebar-settings.tsx`), not one of those four.

This is not the target sidebar (Chat / Strategies / Journal / Research|Portfolio|Signals / Tools|Integrations / Settings).

---

## 4. Settings surfaces

Source of truth for visibility: `SETTINGS_TAB_DEFS` in `lib/entitlements.ts`. The page omits tabs the effective tier cannot use. It does not grey them.

| Effective tier | Tabs shown |
|----------------|------------|
| Observer (`free`), Brief | Notifications, Billing, About |
| Desk | those, plus Brokers |
| Studio, Enterprise, creator floor at Studio | Profile, Pipeline, Keys, Brokers, Notifications, Billing, About |

Deep link resolution (`resolveSettingsTab`): `?tab=` and `?checkout=success|cancel` win, then `#hash`, then the first visible tab. A gated hash is ignored.

API client: `lib/settings-api.ts`. Session JWT to the settings Edge Function (`digiquant/supabase/functions/settings`). Billing checkout and portal are sibling functions. README states Edge deploy is blocked on vault + `broker_connections` (K3). The UI is written against that contract anyway.

There is no free-form model-id picker. Keys seal a provider name only: openai, anthropic, groq, openrouter, xai, gemini.

### Profile (Studio+)

Controls a versioned overlay. Saves append a new version. They do not mutate the tip in place and they cannot edit the reserved `house` key. Optimistic concurrency via last-seen version id (409 reloads).

Investment profile (`lib/settings/schemas/investment_profile.v1.json`): `risk_tolerance`, `horizon_years` (1–50), `liquidity_needs`, `base_currency`, `tax_jurisdiction`, `esg_preference` (`none` \| `tilt` \| `strict`), `excluded_sectors`, `experience_level` (`novice` \| `intermediate` \| `expert`).

Asset preferences (`asset_preferences.v1.json`): named `watchlists`, `custom_universe`, `excluded_tickers` (win over inclusion), `excluded_sectors`.

Persistence name in code and README is still the retired `olympus_profile_config` table. That string is a storage identifier, not a UI label. Do not surface it.

### Pipeline (Studio+)

Overlay knobs on the same profile tip: watchlist, themes, `research_budget_usd`.

Schedule: 7 weekdays × 3 stages (`research`, `deliberation`, `execution`) from `pipeline_schedule.v1.json`. Defaults all on.

Execution policy (`execution_policy.v1.json`): `calendar_mode` is fixed to `venue_calendar`. `on_closed_session` is fixed to `defer`. `respect_early_close` defaults true. `permitted_venues` is an optional preference list. A scheduled execution day cannot force a closed session.

Also reads `GET /settings/jobs` (skip reasons such as `no_credentials`). A hop counts as proven only when status is `succeeded`.

### Keys (Studio+)

Seal and revoke BYOK LLM keys. After save the UI shows fingerprint, provider, status, `last_used_at`. House research keeps operator keys. Overlay jobs are the ones that unseal the user key.

### Brokers (Desk+)

- Alpaca OAuth: `env=paper`, `state` in sessionStorage, return path `/settings/brokers/callback`.
- Alpaca API key: paper only.
- IBKR API key: beta copy, still paper.
- List rows: fingerprint, broker, env, status, `last_used_at`. Secrets are stripped (`SAFE_KEYS` in `brokers-tab.tsx`).
- `GET /settings/fills`: paper-fill fingerprints. A fill proves the hop only together with an Alpaca paper OAuth connection. An API-key paper row does not.

Live venue connect is not in this UI.

### Notifications (all plans)

PATCH prefs: `daily_digest`, `holding_change_alerts`, `execution_alerts`. Digest hour is not a free control in the tab (copy says the saved email and toggles are what dispatch uses).

`GET /settings/notifications/log` lists delivery events. The digest remaining-hop needs a `digest:` log key, inbox confirmation, and `daily_digest` on. Inbox confirmation is operator-side, not a checkbox the member can self-prove.

### Billing (all plans)

Links to checkout and customer portal for Brief, Desk, and Studio. Observer is free and is not a Stripe product. Display catalog in README: Brief $10/mo or $96/yr, Desk $30/mo or $288/yr, Studio $100/mo or $960/yr. Default interval is annual. If annual prices are unset and checkout returns `PRICE_NOT_CONFIGURED`, the UI falls back to monthly. "Billing not configured" when Supabase URL is absent or `NEXT_PUBLIC_STRIPE_BILLING_ENABLED=0`.

The About panel must not render Stripe ids.

### About (all plans)

`RemainingHopStatus` plus `SettingsContent` (version, data-source host, command palette). Member-scoped reads. Observer can see unproven hops without being able to write Studio fields.

Remaining hops (`lib/remaining-hops.ts`):

| Hop id | Meaning |
|--------|---------|
| `browser_stripe_checkout` | Studio/enterprise subscription evidence. Brief or Desk checkout does not prove it. |
| `alpaca_paper_oauth_connect` | Active Alpaca paper OAuth. API key does not prove it. |
| `overlay_daily_claimed` | Overlay job `succeeded`. |
| `paper_fill_mirrored` | A fill with a symbol plus Alpaca paper OAuth. |
| `digest_email_received` | Digest log + inbox confirmed + pref on. |

Blockers are a closed vocabulary (`plan_tier_not_studio`, `missing_stripe_ids`, `subscription_not_active`, `alpaca_api_key_not_oauth`, `no_alpaca_paper_oauth`, `overlay_persist_disabled`, `overlay_legacy_book_unique`, `overlay_not_succeeded`, `fill_without_oauth`, `no_paper_fill`, `digest_pref_off`, `no_digest_log`, `digest_inbox_unconfirmed`).

### Settings routes that are not tabs

`/settings/brokers/callback` completes Alpaca paper OAuth and returns to Brokers. It is not a seventh settings section.

---

## 5. Wired vs stub

The dashboard has **no MCP client**. A search of `apps/dashboard` for MCP imports is empty. digiquant tools (`run_backtest`, `optimize_strategy`, and the rest) stay on the digigraph/digiquant side. Nothing in this UI calls them.

| Surface | Backend | Wired or stub |
|---------|---------|----------------|
| Brief, Portfolio holdings/theses, ticker dossier | Workers API. `DashboardProvider` requires `NEXT_PUBLIC_DASHBOARD_API_URL` and loads `getFullDashboardData()` plus `GET /portfolio`, `/brief`, `/performance`. | **Wired** when the worker is configured. Unconfigured or failed fetch trips the DB-down gate (Brief and Portfolio are not exempt). |
| Tearsheet, Ledger, Attribution, run health | Workers allowlisted table reads and specific routes (`/kpis/live`, `/nav-series`, `/benchmarks`, `/ledger`, observability queries). Market marks: `GET /v1/market/closes` and `GET /v1/market/tickers` when `NEXT_PUBLIC_MARKET_DATA_URL` is set. Empty market config fails closed to an em dash. No Supabase price fallback. | **Wired.** Entitlement can lock the page before fetch (`house_weights_nav`). |
| Pipeline topology and call trace | Same worker. Trace view is `run_event_trace` (legacy compat view name dropped). | **Wired** for persisted artifacts. State-only nodes and missing Inputs calls are labeled gaps, not filled with invented rows. |
| twelve-x | Its own Supabase project (`lib/twelve-x/supabase.ts`, `isTwelveXConfigured`). Not the main dashboard API. DB-gate exempt. | **Wired** when that project is configured. Product gate (`ClientProductGate`, invite redeem) in front. |
| Settings writes | Settings Edge Function, JWT. | **Client wired.** Server deploy of the function is documented as blocked on K3. Treat production proof as unconfirmed from this repo read. |
| Billing | Stripe checkout/portal Edge Functions. | **Wired** when Supabase URL is set and billing is not forced off. Otherwise an explicit not-configured state. |
| Auth | Supabase Auth PKCE. | **Wired behind a flag.** Default flag off. Cloudflare Access is the hosting gate until cutover (`AUTH.md`). |
| digichat popup | digichat embed origin, plan-proof HMAC, operator LLM keys. | **Wired for Desk+** when env and CSP `frame-src` allow it. Baseline is an upgrade panel, not a stub chat. |
| Vela spike | `GET /bars` on digiquant (`NEXT_PUBLIC_DIGIQUANT_BASE_URL`, default `http://127.0.0.1:8001`). Keyless Gloomberb history. Headless `@luxalgo/vela` with offline `data`. QuantCharts is an outbound link to `https://app.luxalgo.com/`. | **Wired as a research spike, not the app chart backbone.** Copy says bars must not feed validate → backtest → optimize → export. |
| Gloomberb | External terminal URL in the sidebar. Per-ticker links (`gloomberbTickerUrl`) on holdings, theses vehicles, deliberations, ticker dossier. twelve-x calendar prefers gloomberb rows over forexfactory twins. | **Destination and data source. Not an in-app terminal.** |
| House profile pins | Static constants in `lib/house-identity.ts`. Corpus sample keys come from loaded docs and fail soft. | **Declared chrome.** README says editable profile waits on ProfileConfig DB. Settings Profile is the real editor for non-house overlays. |
| Strategy builder | — | **Absent.** |
| Trade journal | — | **Absent.** |
| Live broker / live execution UI | — | **Absent.** Paper connect is the only broker write. |
| Chart engines on book surfaces | `lightweight-charts` for time series (`lib/lw-chart.tsx`), recharts for categorical/composition, SVG finance-tearsheet primitives for the print tearsheet. | **Wired to book data.** They are the current stack and conflict with the LuxAlgo-backbone lock. See design debt. |
| Screenshot fixtures | `apps/dashboard/fixtures/screenshots/` | **1×1 placeholders** (24 PNGs, 70 bytes each). Not pictures of the product. |

`examples/bff-snapshots-route.example.ts` is an example, not a route in the static export.

---

## 6. Feature state (product lock checklist)

### Strategy builder

Absent. `/strategy` redirects to theses. digiquant-web `/strategies` is a public tearsheet gallery of published backtests. That gallery stays on the showcase. It is not the in-app builder and it is not a second tool surface.

### Chat

digichat popup only, and only as an entitled embed. It sends sanitized page HTML and visible text as prompt prefix. It does not render a dashboard-native transcript, and it does not build or save a strategy. Observer/Brief see a CTA. Target sidebar label "Chat" does not exist.

### Journaling

Absent. Do not rename Ledger to Journal. Ledger is the house paper book's position-event log.

### Charts and LuxAlgo

Book and FX charts do not use LuxAlgo.

| Engine | Where | Notes |
|--------|-------|-------|
| lightweight-charts | `components/portfolio/DecisionEdgeChart.tsx` via `lib/lw-chart.tsx` | Time series. Canon note in `lib/CHARTS.md` is historical for this app. |
| recharts | Sleeve stack, attribution bars, conviction buckets, parts of twelve-x consensus | Categorical or stacked composition. |
| SVG tearsheet | `components/tearsheet/DashboardTearsheetView.tsx` (`TimeSeries`, `SignedBars` from `@digithings/ui`) | Print/PDF path. Not canvas. |
| `@luxalgo/vela` | `components/research/VelaSpikeChart.tsx` on `/research/vela-spike` only | Headless, offline data, attribution link required. |

A rebuild that keeps lightweight-charts or recharts as a second product chart stack violates the LuxAlgo lock. The spike is the only in-app LuxAlgo embed to study. Gloomberb remains the price source for that spike, not a chart to clone.

### Brokers

Desk+ paper Alpaca (OAuth and API key) and IBKR beta API key. Fills list is paper. Live is coming-soon. Human gate before any live cutover stays in force (`docs/vision/digiquant.md`, `docs/vision/dashboard.md`).

### Tearsheets

`/portfolio/performance` is the operator tearsheet: accounting NAV (`public_accounting_nav_history` via `getPerformanceBundle`), benchmark excess, contribution, open-position outcomes. Closed fills stay on Ledger. Legacy `/performance` and `/portfolio/period` redirect here.

This is the house paper book tearsheet. It is not the digiquant-web strategy-library tearsheet.

### Pipelines

`/pipeline` is the operator view of the daily research → portfolio graph (stages in section 3). It is wired to persisted documents and `run_event_trace`. Settings Pipeline is a different thing: weekday schedule and overlay budget for a Studio workspace, not the glass-box.

### Research / portfolio / signals

Job words in the current UI are Brief, Portfolio, Pipeline, Holdings, Theses, Tearsheet, Ledger, Attribution. There is no sidebar item named Research or Signals. Research artifacts are Pipeline nodes and the Why "read" tab. Signals show up inside Brief and deliberations, not as their own destination.

---

## 7. Design debt and reference-only material

Keep these as evidence. Do not re-skin them into the new shell.

| Item | Why it is debt or reference-only |
|------|----------------------------------|
| Current sidebar IA (Brief / Portfolio / Pipeline / FX Hub) | Real product today. Not the target top-level list. |
| Collapsed sidebar (`md:w-[72px]`, label `md:sr-only`) | Icon-only rail. Target lock is literal labels, never icon-only. |
| Icons inside section tabs (Portfolio, Why, twelve-x) | Tab bar reference asks for literal words. Icons are extra, not a substitute, but the collapsed sidebar is the actual violation. |
| `/why` still mounted | Legacy reader next to Pipeline. Bookmarks and the DB-exempt list do not send `/why` to Pipeline. `/research` and `/library` do. |
| `/strategy` name | Implies a builder. It is a theses redirect. |
| Geist Mono as the only voice (`app/layout.tsx`, "BLEND v0.1") | Current app. Craft lock for the rebuild is Inter + JetBrains Mono. |
| `packages/design/references/dashboard-subpage-chrome.md` | Still the sticky-tab and flat-surface reference (blur only on sticky/overlay, `--surface`, `--hair`). Its type section still says Instrument Serif and Geist. That type note loses to the Inter + JetBrains Mono lock. |
| `lib/CHARTS.md` lightweight-charts ruling | Accurate for the current book charts. Superseded as a future chart-stack decision by the LuxAlgo backbone lock. |
| Parked #4885, #4892, #4896 | Reference only. Craft follows #4885 (digiquant-web), not the fat #4896 shell. No visual polish in this lane. |
| `docs/dashboard-audits/DASHBOARD_FRONTEND_AUDIT.md` (2026-06-17) | Historical. It describes empty actions and zeroed metrics from that date. Do not treat it as the current wiring map. Section 5 of this file is the current code map. |
| `docs/superpowers/plans/2026-06-24-twelve-x-dashboard-redesign.md` and other `olympus-*` plan titles | Historical plans. Retired codenames must not re-enter UI labels. |
| Screenshot PNGs under `apps/dashboard/fixtures/screenshots/` | Contract fixtures for Pipeline stages and artifact families (`lib/screenshot-manifest.ts`). All 24 files are 70-byte placeholders. Not visual reference. |
| `apps/digiquant-web` landing `DashboardScene` / `DashboardPortfolioPanel` | Showcase illustration. Not the operator app. |
| Retired identifiers still in code | `olympus_profile_config` table name, `olympus-theme` legacy localStorage key (`components/theme-provider.tsx`, read-and-migrate only), comments and generated DB types that mention the old trace view. UI strings checked in this pass use job words (Brief, Portfolio, Pipeline, research, portfolio, execution). Do not "fix" storage names in a UI rebuild. |
| House page off-nav | Easy to miss in a route audit. It is a lab must-have and it exists. |
| Dual "Pipeline" words | Glass-box route vs Settings tab. A new IA has to keep them distinct. |
| Entitlement copy in page comments | Some comments still say "Baseline+". Product names are Observer / Brief / Desk / Studio. `house_weights_nav` unlocks at Brief. |

What is worth keeping as behavior, regardless of chrome:

- Paper default and calendar veto (`defer` on a closed session).
- Fail closed: missing marks, missing fills, and locked tiers render an em dash or a locked surface, not invented P&L.
- One NAV series for Brief and Tearsheet (`getPerformanceBundle`). Live marks are an overlay badge, not a second set of books.
- Settings tabs omitted by tier, hash and `?tab=` deep links, no model-id picker.
- Static-export query routes for thesis id and ticker (no dynamic segment that 404s after deploy).
- Access gate. Auth flag plus hosting access. FX Hub is a client product, not a public page.
- Gloomberb and LuxAlgo as links or embeds, not cloned terminals.
- No private-client names in chrome.

---

## 8. Screenshot and file inventory

No new screenshots were taken. This lane does not run the UI.

Pipeline glass-box fixture contract (`fixtures/screenshots/manifest.json`):

- Stages × desktop/mobile: inputs, research, synthesis, selection, decision, learning.
- Artifact families: attention-plan, research-segment, fanout-alt-data, fanout-analyst, digest, deliberation, pm-direction, pm-rebalance, commit, beliefs, call-trace, artifact-ledger.
- On disk: 24 PNGs, each 70 bytes. Placeholders until an operator capture replaces them. Vitest only checks path and PNG magic.

Key source files for a later lane (read these, do not clone the shell):

| Concern | Path |
|---------|------|
| Nav | `apps/dashboard/lib/nav.ts` |
| Frame | `apps/dashboard/components/app-frame.tsx`, `components/sidebar.tsx` |
| Redirects | `apps/dashboard/components/legacy-spa-redirect.tsx` |
| Brief | `apps/dashboard/app/page.tsx`, `components/today/daily-brief-workspace.tsx` |
| Portfolio | `apps/dashboard/components/portfolio/PortfolioShellInner.tsx`, `PortfolioSectionNav.tsx` |
| Tearsheet | `apps/dashboard/app/portfolio/performance/page.tsx` |
| Pipeline | `apps/dashboard/app/pipeline/page.tsx`, `lib/pipeline-topology.ts` |
| Legacy Why | `apps/dashboard/app/why/page.tsx`, `lib/why-tabs.ts` |
| House | `apps/dashboard/app/house/page.tsx`, `lib/house-identity.ts` |
| Settings | `apps/dashboard/app/settings/page.tsx`, `lib/entitlements.ts`, `lib/settings-api.ts` |
| Auth | `apps/dashboard/lib/auth-gate.tsx`, `apps/dashboard/AUTH.md` |
| Ticker | `apps/dashboard/app/portfolio/tickers/page.tsx` |
| Vela spike | `apps/dashboard/app/research/vela-spike/page.tsx`, `lib/vela-bars.ts` |
| digichat embed | `apps/dashboard/components/digichat-popup.tsx`, `lib/digichat-popup.ts` |
| Data load | `apps/dashboard/lib/dashboard-context.tsx`, `lib/api-client.ts` |
| Product vision | `docs/vision/dashboard.md`, `docs/vision/digiquant.md` |
| Settings IA | `docs/agent-backlog/execution-tenancy/SETTINGS-IA.md` |
| Subpage chrome reference | `packages/design/references/dashboard-subpage-chrome.md` |

---

## 9. Lane boundary

Lane 1 is this inventory.

Lane 2 (not started here) would propose the new information architecture against the target sidebar and the lab spine, using coming-soon rules for builder, journal, live brokers, and first-class digichat.

Lane 3 (not started here) would be craft, and only after IA is accepted. It follows digiquant-web #4885, LuxAlgo as the chart embed, and Gloomberb as a destination. It does not re-skin #4896.

No implementation tasks belong in this file.
