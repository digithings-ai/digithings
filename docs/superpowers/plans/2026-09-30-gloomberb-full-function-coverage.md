# Gloomberb Full Function Coverage (130/130) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every one of the 130 functions on https://gloom.sh/docs/functions (snapshot 2026-09-30) is mapped to a digiquant tool, a native digiquant capability, or a declared out-of-scope reason, so "complete gloomberb integration" is a checkable claim.

**Architecture:** Extend the existing `digifetch_*` vertical slice (models → `GloomberbClient` method → `TOOL_ENTITLEMENTS` free/session/pro/proxy → orchestrator manifest builder → `DIGIFETCH_DISPATCH` row → MCP wrapper + `READ_SCOPE_TOOLS` → subset) to three new method kinds: pure calculators (no transport, still enveloped), compositions (client methods calling existing client methods, inheriting cache/kill-switch), and session-gated writes/orders (two-phase approval). No second HTTP client; venue-direct precedent (`prediction_markets`, #4819) applies to FNG/POLL/AUCT/HALT/IPO/HN.

**Tech Stack:** Python 3.12, Pydantic v2, httpx + `digifetch.HttpFetcher` (rate limiter, retry, breaker, 900s cache, SSRF guard), FastMCP, existing offline-test pattern (`httpx.MockTransport`, no live calls without operator approval).

**Spec:** https://gloom.sh/docs/functions (130 functions, snapshot 2026-09-30 in Task 0); gloom-sh org plugin sources (`gloom-prediction-markets`, `gloom-polls`, `gloom-fear-greed`, `gloom-ipo-calendar`, `gloom-market-halts`, `gloom-hackernews`, `gloom-substack`, `gloom-tv`, `gloom-ibkr-gateway`, `gloom-simplefin`, `gloom-public`, `gloom-robinhood`, `gloom-byok-ai`) for exact upstream shapes; `digiquant/ARCHITECTURE.md` § gloomberb (update the stale "prediction markets (kelly-sizer is a local model with no data endpoint)" line at ~:1363 as part of Task 9).

## Global Constraints

- Polars only — never pandas (new code adds no pandas imports).
- Pydantic v2 everywhere; strict typing; ruff-compliant, line length 100.
- TDD: no production code without a failing test first; watch it fail, then green.
- Tests are offline: `httpx.MockTransport` only; live probes need explicit operator approval per call.
- Every tool returns `DigifetchEnvelope[T]`; tools never raise (typed `DigifetchError`: `auth_required` / `pro_required` / `not_found` / `rate_limited` / `upstream_error` / `invalid_input`).
- Contract violations are rejected (`invalid_input`), never clamped.
- Venue-direct data must NOT claim "Sourced from Gloomberb" and must NOT emit `term.gloom.sh` links (precedent: `prediction_markets` #4819 — `provider_id="prediction-markets-venues"`, `attributed=False`, per-row venue URLs).
- Digi product names always lowercase in prose/docs (`digiquant`, `digifetch`); code identifiers keep language casing.
- New external service dependencies and broker/order paths: implementation PRs do NOT self-merge (human gate). Approval-gated orders (Task 7) need human review of the gate design itself before the execute path is enabled.
- `GLOOMBERB_ENABLED` kill switch gates the whole family including calculators/compositions (uniformity over cleverness).
- Subsets `EQUITY_TOOLS` / `MACRO_TOOLS` / `PM_TOOLS` stay ≤16 names each and pairwise distinct as frozensets (parity test enforced).

---

## Coverage matrix (the 130, locked)

Status key: DONE (shipped) · CALC (pure calculator, Phase A) · COMP (composition over tooled routes, Phase A) · PROBE (needs endpoint probe, Phase B) · TOS (direct-to-venue with caveats, Phase C) · WRITE (workspace write, Phase D) · GATE (approval-gated, Phase E) · NATIVE (digiquant-native, no gloomberb tool) · OUT (declared out-of-scope with reason).

Research companies (45): DES DONE · QQ DONE · GP DONE · GIP DONE · TAS PROBE · QR PROBE · G COMP · CAT DONE · FAM DONE · DDIS PROBE · HP DONE · CMP COMP · GFM COMP · GE COMP · GR COMP · CORR COMP · BT NATIVE (`digiquant_run_backtest`) · RV COMP · EQS DONE · OMON DONE · OVME CALC · OSA CALC · OVDV PROBE · HIVG/HVG/HVT PROBE · VCA PROBE · ANR DONE · EE PROBE · EMM PROBE · GUID COMP-over-transcripts (fallback PROBE) · EVT DONE · DVD COMP (yield over corporate_actions + quote) · SI DONE · SIV PROBE · DIAG DONE · RISK DONE · EXEC DONE · EK DONE · CALLS DONE · JOBS PROBE · SRCH DONE · AI/AGENT OUT (BYOK key, no data endpoint) · ASKG OUT (Cloud AI chat, no data endpoint).
News (9): TOP/N/CN/NI/FIRST DONE · TWIT DONE · SUB PROBE (auth-gated reader) · TV OUT (live video pane, no tool surface) · HN TOS (public API reader).
Markets (20): MOST DONE-partial (screener; trending/pre-market = PROBE) · WEI/BI/RRG/HM COMP (index/ETF baskets over quotes_batch) · FXC COMP (USD-pair matrix over exchange_rate) · CRYP PROBE (coin list source) · FUT/CTM OUT (Yahoo continuous symbols, prior decision) · FNG TOS (CNN unofficial ToS note) · COT PROBE · VIX/VOLS COMP (FRED composition over econ_series) · HILO PROBE · FLOW PROBE (pro) · HALT TOS (Nasdaq Trader public) · IPO TOS (Cloud-overlap check first) · MAP DONE · PM DONE · POLL TOS (VoteHub CC BY 4.0 attribution).
Macro (14): ECO DONE · ECST DONE · CBR PROBE · GC DONE · WIRP COMP (fed-prob ladder over existing ingest + kalshi/ polymarket reads) · CRD PROBE · AUCT TOS (fiscaldata direct) · BTMM COMP (SOFR/EFFR/reserves are FRED series) · CDS DONE · CDX/SOVR PROBE · YAS CALC · VAL COMP (Shiller + econ_series) · ERN DONE.
Ownership (5): SEC DONE · HDS DONE · 13F DONE · INS PROBE (Form 4) · CG DONE.
Workspace (12): PF/PORT WRITE (probe Cloud write API first; read-only if no write route) · KELLY CALC · AW/AP/RW/RP WRITE · ALRT/SA WRITE · NOTE WRITE · THESIS WRITE (read-only if no write route) · VIEW WRITE (spec JSON Kroner; read-only if no write route).
Cloud/brokers (9): CHAT/DM/TEAM/FOCUS/TBO/ACM/UPGRADE OUT (account surfaces, no data API) · BR GATE (read-only positions/account sync) · IBKR GATE (two-phase orders).
Layouts/settings (16): ALL OUT (app chrome, no API surface: GL, LAY, LMA, WIN, PS, PL, TH, LANG, FONT, SB, VF, CR, CONN, CHG, HELP, FB).

"Complete integration" = every function carries one of these statuses, each with a tool or a written reason. OUT items are listed in ARCHITECTURE with reasons, not silently dropped.

---

### Task 0: Coverage matrix spec doc

**Files:**
- Create: `docs/superpowers/plans/2026-09-30-gloomberb-function-matrix.md`
- Test: n/a (docs; validated by `make doc-check` in Task 9)

**Interfaces:**
- Consumes: https://gloom.sh/docs/functions (130 count verified 2026-09-30)
- Produces: the per-function status table every later task argues from

- [ ] **Step 1: Write the matrix doc** containing the 130-prefix table from this plan's Coverage matrix section (prefix, docs title, status, mapped tool name or reason). Include the snapshot date and the definition of done above.
- [ ] **Step 2: Run doc links check**

Run: `make doc-check`
Expected: PASS
- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-09-30-gloomberb-function-matrix.md
git commit -m "docs(digiquant): gloomberb 130-function coverage matrix (#4813 follow-up)"
```

---

### Task 1: Calculator core (OVME, YAS, KELLY)

**Files:**
- Create: `digiquant/src/digiquant/data/gloomberb/calculators.py`
- Test: `tests/dq/data/test_gloomberb_calculators.py`

**Interfaces:**
- Consumes: nothing (pure stdlib `math` + `statistics`)
- Produces: `black_scholes_price(*, spot, strike, rate, vol, expiry_years, kind) -> float`, `black_scholes_iv(*, price, spot, strike, rate, expiry_years, kind) -> float`, `bond_metrics(*, coupon, face, ytm, years, freq) -> dict` (price, accrued, duration, convexity, dv01), `kelly_fraction(*, win_prob, win_loss_ratio) -> float`

- [ ] **Step 1: Write the failing tests**

```python
def test_black_scholes_call_put_parity() -> None:
    from digiquant.data.gloomberb.calculators import black_scholes_price

    call = black_scholes_price(spot=100.0, strike=100.0, rate=0.05, vol=0.2, expiry_years=1.0, kind="call")
    put = black_scholes_price(spot=100.0, strike=100.0, rate=0.05, vol=0.2, expiry_years=1.0, kind="put")
    assert call - put == pytest.approx(100.0 - 100.0 * math.exp(-0.05), rel=1e-9)


def test_kelly_rejects_impossible_probability() -> None:
    from digiquant.data.gloomberb.calculators import kelly_fraction

    with pytest.raises(ValueError):
        kelly_fraction(win_prob=1.5, win_loss_ratio=1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/data/test_gloomberb_calculators.py -v`
Expected: FAIL with "No module named 'digiquant.data.gloomberb.calculators'"
- [ ] **Step 3: Write minimal implementation** (`calculators.py` with the four functions; Black-Scholes via `math.erf` cdf; IV via bisection capped at 200 iterations raising `ValueError` on non-convergence; Kelly clamps negative to 0.0 and raises `ValueError` outside [0, 1])
- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dq/data/test_gloomberb_calculators.py -v`
Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/data/gloomberb/calculators.py tests/dq/data/test_gloomberb_calculators.py
git commit -m "feat(digiquant): gloomberb calculator core OVME/YAS/KELLY (130-coverage)"
```

---

### Task 2: Calculator + composition tool wiring (OVME, YAS, KELLY, DVD, FXC, VIX)

**Files:**
- Modify: `digiquant/src/digiquant/data/gloomberb/models.py` (add `OptionsCalcInput`, `BondCalcInput`, `KellyInput`, `DividendYieldInput`, `FxMatrixInput`, `VixTermInput` + row/result/envelope types)
- Modify: `digiquant/src/digiquant/data/gloomberb/client.py` (add `options_calculator`, `bond_calculator`, `kelly_sizer`, `dividend_yield`, `fx_cross_rates`, `vix_term_structure` methods)
- Modify: `digiquant/src/digiquant/data/gloomberb/entitlements.py` (six `"digifetch_*": "free"` rows)
- Modify: `digiquant/src/digiquant/orchestrator_tools.py` (six `build_digifetch_*_tool()` builders + manifest list entries; descriptions name the math source, never "Gloomberb Cloud")
- Modify: `digiquant/src/digiquant/data/gloomberb/agent_tools.py` (six `DIGIFETCH_DISPATCH` rows, `attributed=False`, no `symbol_field`)
- Modify: `digiquant/src/digiquant/mcp_server.py` (six `@_maybe_tool` wrappers calling `_gloomberb_envelope_json(envelope, attributed=False)` + six `READ_SCOPE_TOOLS` entries)
- Modify: `digiquant/src/digiquant/data/gloomberb/__init__.py` (re-export new models)
- Test: `tests/dq/data/test_gloomberb_calc_tools.py`

**Interfaces:**
- Consumes: Task 1 (`calculators.*`); existing `client.quote/ticker_financials/corporate_actions/exchange_rate/econ_series` for compositions
- Produces: `GloomberbClient.options_calculator/bond_calculator/kelly_sizer/dividend_yield/fx_cross_rates/vix_term_structure`

Composition rules (locked): `dividend_yield` reads `corporate_actions` (trailing cash distributions) + `quote` (price); warns and returns `upstream_error` when either errors. `fx_cross_rates` reads `exchange_rate` per requested currency vs USD and crosses pairs (USD base only; non-USD `to_currency` is `invalid_input`). `vix_term_structure` reads `econ_series` VIX 30-day/3-month closes and reports contango/inversion. All six honor `_enabled` (`_disabled` envelope) and `_cached` (900s). None attaches cookies. None claims Cloud sourcing.

- [ ] **Step 1: Write the failing test**

```python
def test_options_calculator_puts_parity_without_a_request() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("pure calculators must not reach the wire")

    client = make_client(_fail)
    envelope = client.options_calculator(
        {"spot": 100.0, "strike": 100.0, "rate": 0.05, "vol": 0.2, "expiry_years": 1.0, "kind": "call"}
    )
    assert envelope.data.price > 0.0
    assert calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/data/test_gloomberb_calc_tools.py -v`
Expected: FAIL (`make_client` undefined — copy the helper from `test_gloomberb_agent_tools.py:68-75`; then FAIL on missing `options_calculator`)
- [ ] **Step 3: Write minimal implementation** (models + six client methods + entitlements + manifest builders + dispatch rows + MCP wrappers + exports, per the composition rules above)
- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/dq/data/test_gloomberb_calc_tools.py tests/dq/data/test_gloomberb_agent_tools.py tests/dq/test_mcp_gloomberb_tools.py tests/dq/test_mcp_server_scope.py -m unit -q`
Expected: PASS (update count pins: tools 35→41, read scope 45→51, full 59→65; extend the UNATTRIBUTED set with the six names)
- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/data/gloomberb/ digiquant/src/digiquant/mcp_server.py digiquant/src/digiquant/orchestrator_tools.py tests/dq/
git commit -m "feat(digiquant): digifetch calculators + compositions OVME/YAS/KELLY/DVD/FXC/VIX (130-coverage)"
```

---

### Task 3: Portfolio-math compositions (CMP, GR, CORR, RV, GFM, GE, G, VAL, BTMM, WIRP)

**Files:**
- Modify: `digiquant/src/digiquant/data/gloomberb/models.py`, `client.py`, `entitlements.py`, `orchestrator_tools.py`, `agent_tools.py`, `mcp_server.py`, `__init__.py` (same vertical slice as Task 2)
- Test: `tests/dq/data/test_gloomberb_portfolio_math_tools.py`

**Interfaces:**
- Consumes: existing `client.price_history/ticker_financials/econ_series/shiller`, Task 2 wiring checklist
- Produces: `GloomberbClient.compare_performance/correlation_matrix/relationship_graph/relative_valuation/fundamental_graph/valuation_graph/custom_chart/market_valuation/money_markets/rate_path`

Composition rules (locked): all read `price_history` (rebased returns; date-aligned inner join; `invalid_input` on <2 tickers or empty overlap) or `ticker_financials`/`econ_series`/`shiller`. `custom_chart` (G) takes explicit series list `[{source: price|statement|fred, ref}]` and returns aligned columns (no catalog search). `market_valuation` returns Shiller CAPE + selected econ ratios vs history zones. `money_markets` reads FRED SOFR/EFFR/reserve series ids via `econ_series`. `rate_path` differences the fed-prob survival ladder (reuse `fed_probabilities.fed_distribution_from_ladder` semantics on live Kalshi KXFED reads via the venue path). Subset: add `compare_performance`, `correlation_matrix`, `relative_valuation` to `EQUITY_TOOLS` (13→16, budget check); `market_valuation`, `money_markets`, `rate_path` to `MACRO_TOOLS` (8→11); rest MCP-only.

- [ ] **Step 1: Write the failing test** (correlation matrix over two MockTransport history series asserting `correlation == pytest.approx(1.0)` for identical series, no Cloud claim in payload)
- [ ] **Step 2: Run test to verify it fails** (`pytest tests/dq/data/test_gloomberb_portfolio_math_tools.py -v`, FAIL on missing method)
- [ ] **Step 3: Write minimal implementation** (ten tools, same slice as Task 2)
- [ ] **Step 4: Run tests** (full gloomberb set + scope; update count pins 41→51 tools, 51→61 read, 65→75 full)

Run: `pytest tests/dq/data/ tests/dq/test_mcp_gloomberb_tools.py tests/dq/test_mcp_server_scope.py tests/dq/test_orchestrator_invoke_digifetch.py -m unit -q`
Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/ tests/dq/
git commit -m "feat(digiquant): digifetch portfolio-math compositions CMP/GR/CORR/RV/GFM/GE/G/VAL/BTMM/WIRP (130-coverage)"
```

---

### Task 4: Endpoint probes (TAS, QR, EE, EMM, SIV, JOBS, INS, CBR, CRD, CDX, SOVR, HILO, FLOW, COT, CRYP, VCA, IV-history, DDIS, MOST-trending, SUB, IPO-overlap)

**Files:**
- Create: `docs/superpowers/plans/2026-09-30-gloomberb-endpoint-probes.md`
- Test: n/a (probe report; no code)

**Interfaces:**
- Consumes: gloom-sh org sources (gloomberb repo + plugin repos under /tmp or fresh clone) for exact route shapes; Task 0 matrix
- Produces: per-candidate verdict table (route + params + auth + sample shape, or NO-ROUTE with fallback: compose/defer/OUT)

Rules (locked): source-available TS first (`api-client/`, plugin `services/`); live HTTP only with explicit operator approval per host, one smoke call max, never paste secrets; every verdict names the file:line evidence. IPO must answer the Cloud-overlap question (is there a `/cloud/*` IPO route? if yes, Cloud tool; if no, direct). SUB verdict must state the auth mechanism (own-account sign-in) and fail-soft when absent. Order-flow (FLOW) and IV-history verdicts must state Pro/cloud gating.

- [ ] **Step 1: Clone/read the org sources and fill the verdict table** (one row per candidate: route, method, params, entitlement guess, shape notes or NO-ROUTE + fallback)
- [ ] **Step 2: Self-review the table** (every PROBE-matrix item has exactly one verdict row; no live calls without operator sign-off recorded in the doc)
- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-09-30-gloomberb-endpoint-probes.md
git commit -m "docs(digiquant): gloomberb endpoint probe verdicts for 130-coverage"
```

---

### Task 5: Probe-backed tools (implements Task 4 verdicts)

**Files:** same vertical slice as Task 2 + `ENDPOINTS` additions for confirmed Cloud routes
**Test:** `tests/dq/data/test_gloomberb_probe_tools.py` (+ MockTransport fixtures per new route)

**Interfaces:**
- Consumes: Task 4 verdict table (only GO verdicts become tools; NO-ROUTE items move to compose/defer with matrix update)
- Produces: one `digifetch_*` tool per GO verdict (exact names/params from verdicts)

- [ ] **Step 1: Write the failing test** for the first GO tool (invalid-input-no-request + mapped-rows cases, following `test_mcp_gloomberb_tools.py` conventions)
- [ ] **Step 2: Run test to verify it fails** (FAIL on missing method)
- [ ] **Step 3: Write minimal implementation** (all GO tools in this task's batch)
- [ ] **Step 4: Run tests** (full gloomberb set + scope; update count pins to actuals; extend UNATTRIBUTED only for venue-direct tools)

Run: `pytest tests/dq/data/ tests/dq/test_mcp_gloomberb_tools.py tests/dq/test_mcp_server_scope.py tests/dq/test_orchestrator_invoke_digifetch.py -m unit -q`
Expected: PASS
- [ ] **Step 5: Commit** (`feat(digiquant): digifetch probe-backed tools <names> (130-coverage)`)

---

### Task 6: ToS/direct tools (FNG, POLL, AUCT, HALT, HN, GUID-via-transcripts if Task 4 says NO-ROUTE)

**Files:** same vertical slice; venue constants beside `POLYMARKET_GAMMA_BASE_URL` in `client.py`
**Test:** `tests/dq/data/test_gloomberb_tos_tools.py`

**Interfaces:**
- Consumes: plugin sources for shapes (`gloom-fear-greed`, `gloom-polls`, Nasdaq Trader halt feed, fiscaldata API docs, `gloom-hackernews`)
- Produces: `digifetch_fear_greed`, `digifetch_polls`, `digifetch_treasury_auctions`, `digifetch_market_halts`, `digifetch_hacker_news`, (`digifetch_company_guidance` iff NO-ROUTE)

Locked caveats (copy-verbatim into descriptions + ARCHITECTURE): FNG "unofficial CNN read, ToS grey area, cross-check before citing"; POLL carries "VoteHub data © VoteHub contributors, CC BY 4.0" per-row attribution; AUCT "Treasury Fiscal Data, public"; HALT "Nasdaq Trader, delayed"; HN "public API". All `free`, `attributed=False`, per-row source URLs, per-venue fail-soft. GUID-via-transcripts composes `transcripts` text (guidance extraction is best-effort quote harvesting, labeled as such, never advice).

- [ ] **Step 1: Write the failing test** (FNG maps 7 components + index; POLL rows carry the CC BY marker; no Gloomberb claim anywhere)
- [ ] **Step 2: Run test to verify it fails** (FAIL on missing method)
- [ ] **Step 3: Write minimal implementation**
- [ ] **Step 4: Run tests** (full gloomberb set + scope; update count pins)

Run: `pytest tests/dq/data/ tests/dq/test_mcp_gloomberb_tools.py tests/dq/test_mcp_server_scope.py -m unit -q`
Expected: PASS
- [ ] **Step 5: Commit** (`feat(digiquant): digifetch ToS/direct tools FNG/POLL/AUCT/HALT/HN (130-coverage)`)

---

### Task 7: Workspace writes + broker reads + approval-gated orders

**Files:** same vertical slice + `digiquant/src/digiquant/data/gloomberb/approvals.py` (NEW: ticket issue/redeem)
**Test:** `tests/dq/data/test_gloomberb_workspace_broker_tools.py`

**Interfaces:**
- Consumes: Task 4 Cloud-write-API verdicts (no write route → read-only tool + matrix note, no write tool invented)
- Produces: `digifetch_portfolio_view` (read), write tools (`watchlist_add/remove`, `portfolio_add/remove`, `alert_add/list`, `note_add`, `thesis_add`, `view_add`) each gated `session` (cookie required, zero-HTTP `auth_required` without it); `digifetch_broker_positions` (read-only, `session`); `digifetch_ibkr_preview_order` (returns ticket, never executes) + `digifetch_ibkr_execute_order` (requires `approval_token` from `approvals.issue_ticket`, single-use, 15-min TTL, ticket-hash-bound; without valid token → `invalid_input`, no request)

Approval-gate rules (locked, human-reviewed before execute path enables): ticket binds symbol/side/quantity/order-type/limit; token is HMAC over ticket + expiry with server-side key from env (never committed); execute validates token, quantity>0, and `GLOOMBERB_ENABLED`; every call logs symbol/side/quantity to the audit log WITHOUT the token; dry-run mode returns the would-be request. Until the gate design passes human review, `execute_order` ships returning `upstream_error("order execution disabled pending approval-gate review")` with zero brokerage traffic — the preview path works immediately.

- [ ] **Step 1: Write the failing test** (execute without token → `invalid_input`, zero HTTP calls; preview returns ticket with no traffic)
- [ ] **Step 2: Run test to verify it fails** (FAIL on missing module)
- [ ] **Step 3: Write minimal implementation** (approvals module + tools; execute path disabled-flag ON until review)
- [ ] **Step 4: Run tests** (full gloomberb set + scope; update count pins; assert new write tools are `session`-entitled in `test_declared_entitlements_match_the_gate_behavior`-style coverage)

Run: `pytest tests/dq/data/ tests/dq/test_mcp_gloomberb_tools.py tests/dq/test_mcp_server_scope.py -m unit -q`
Expected: PASS
- [ ] **Step 5: Commit** (`feat(digiquant): digifetch workspace writes + approval-gated broker orders, execute disabled (130-coverage)`)

---

### Task 8: OSA (options scenario over options_chain)

**Files:** same vertical slice (one tool); reuses Task 1 math + `options_chain` rows
**Test:** extend `tests/dq/data/test_gloomberb_calc_tools.py`

**Interfaces:**
- Consumes: `client.options_chain`, `calculators.black_scholes_price`
- Produces: `GloomberbClient.options_scenario` (legs: [{expiry, strike, kind, qty}]; value at spot/date/vol-shift grid; payoff, P&L, breakevens, Greeks; European-only label)

- [ ] **Step 1: Write the failing test** (single long call values to Black-Scholes at spot=strike; breakeven == strike + premium)
- [ ] **Step 2: Run test to verify it fails** (FAIL on missing method)
- [ ] **Step 3: Write minimal implementation**
- [ ] **Step 4: Run tests** (calc + full gloomberb set; update count pins +1)
- [ ] **Step 5: Commit** (`feat(digiquant): digifetch options scenario OSA (130-coverage)`)

---

### Task 9: Docs, counts, review coverage, promotion

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (130-status table pointer + OUT reasons; fix stale prediction-markets line ~:1363; update tool counts), `digiquant/AGENTS.md` (tool-count + new cohorts), `docs/ops/gloomberb-session-cookie.md` (new `session` tools if Task 7 adds any), `docs/superpowers/plans/2026-09-30-gloomberb-function-matrix.md` (final statuses)
- Test: `make doc-check`; full suite below

**Interfaces:**
- Consumes: all prior tasks
- Produces: merge-ready PR with review coverage

- [ ] **Step 1: Update the docs** (counts, matrix final statuses, runbook deltas, stale-line fix)
- [ ] **Step 2: Run the full verification**

Run: `pytest tests/dq/data/ tests/dq/test_mcp_gloomberb_tools.py tests/dq/test_mcp_server_scope.py tests/dq/test_orchestrator_invoke_digifetch.py -m unit -q`
Expected: PASS

Run: `ruff check digiquant/ && ruff format --check digiquant/`
Expected: zero errors

Run: `make doc-check`
Expected: PASS
- [ ] **Step 3: Fresh-context review** (author session must NOT review its own work: dispatch `/review` or in-session fresh-context subagent; post findings with `<!-- in-session-review -->`; apply `reviewed:agent`)
- [ ] **Step 4: Open the PR** against `module/digiquant` (two-hop base), title `feat(digiquant): gloomberb 130-function coverage (<issue>)`, body with matrix link + per-task summary + human-gate notes (new external deps; order-gate design needs human review before execute enables). Do NOT merge: human gate owns the merge.
- [ ] **Step 5: Commit** any final doc fixes separately (`docs(digiquant): 130-coverage docs + counts`)

---

## Self-review

1. **Spec coverage:** all 130 prefixes appear in the matrix with exactly one status; every CALC/COMP/PROBE/TOS/WRITE/GATE item has an implementing task (0–8); OUT items (AI, AGENT, ASKG, TV, FUT, CTM, CHAT, DM, TEAM, FOCUS, TBO, ACM, UPGRADE, 16 layout/settings) are listed with reasons in Task 9 docs; NATIVE (BT) maps to `digiquant_run_backtest`. Gaps: none found — GUID has a COMP primary with PROBE fallback; MOST-trending folds into Task 4; IPO-overlap folds into Task 4.
2. **Placeholder scan:** no TBD/TODO/"similar to" without content — Tasks 2/3/5/6 repeat the full vertical slice file list; the only shared reference is the named "wiring checklist" (Task 2), which is itself fully specified.
3. **Type consistency:** `DigifetchDispatch(Model, "method", attributed=False)` shape matches `agent_tools.py:300-307`; `_gloomberb_envelope_json(envelope, attributed=False)` matches the parsed MCP contract (`test_dispatch_link_and_attribution_match_the_mcp_wrappers`); count-pin updates are flagged in every implementing task.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-30-gloomberb-full-function-coverage.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session, batch execution with checkpoints

**Which approach?**
