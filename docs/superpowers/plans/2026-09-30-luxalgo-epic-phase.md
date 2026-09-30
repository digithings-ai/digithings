# LuxAlgo Epic Phase (P0-2, P0-3, P1-4, P1-5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the remaining in-scope LuxAlgo wrap/connect work from epic #4779: CC0 public-records ingest (P0), honesty envelope for stats (P0), read-only broker golden path (P1), and a time-boxed Vela chart spike (P1).

**Architecture:** Four independent workstreams, each a thin wrap mirroring an established in-repo pattern (Gloomberg client/dispatcher seam, research-ingest path, mocked-transport broker tests, dashboard component). No new services, no live-trading changes, no hosted credentials.

**Tech Stack:** Python (Pydantic v2, Polars-only, httpx, pytest `-m unit`), TypeScript/React dashboard (`@luxalgo/vela`), CC0 JSON dumps over HTTPS via digifetch.

**Spec:** `/Users/chrisstefan/Code/luxalgo-digiquant-scope.md` (§§3, 5.3–5.4, 6, 7) + child issues #4826, #4828, #4829, #4830. P0 item 1 (hosted MCP Library wrap) is done — PR #4816, package `digiquant/src/digiquant/data/luxalgo/`.

## Global Constraints

- Digi product/module names always lowercase in prose, docs, commits, PR text (`digithings`, `digiquant`, `digisearch`, …). Code identifiers keep language casing.
- Polars only — never pandas (new code; `tearsheet*.py` pandas allowlist is grandfathered, do not extend it).
- Pydantic v2 everywhere; strict typing; ruff line length 100 (`ruff check . && ruff format .`).
- Every change traces to its child issue: `task/<N>-slug` branch (via `make task ISSUE=N`) + `Refs #4779` in PR body. Never `Fixes #4779` until the wave is done.
- No broker secrets to hosted MCP (hosted has no broker tools by design). All tests offline — mocked transports, no live HTTP, no real keys in fixtures.
- Never touch live-trading execution paths without explicit human approval. #4829 (brokers/) requires human review before merge.
- Library indicator source (CC BY-NC-SA) stays out of paid surfaces — no `library_get_source_code` wiring anywhere.
- Do not treat edge/pass % as predictions in UX — ship the fixed disclaimer verbatim.
- Do not fork/rebrand LuxAlgo OSS (trademark); ship LICENSE/NOTICE copies where licenses require.
- Review coverage per `docs/agents/CODE_REVIEW_POLICY.md` before merge; merge into the workstream's base branch (see lanes below).

## Merge lanes (do not mix)

| Workstream | Issue | Code area | Branch base |
|---|---|---|---|
| A trackers ingest | #4826 | digisearch | `module/digisearch` |
| B honesty envelope | #4828 | digiquant (stats + tearsheets) | `module/digiquant` |
| C broker Alpaca read-only | #4829 | digiquant (brokers + briefing) | `module/digiquant` |
| D Vela spike | #4830 | apps/dashboard | `develop` (no routing entry → default) |

B and C share a base but touch disjoint dirs (`stats/`, `tearsheet*.py`, `charts/` vs `brokers/`, `research/`, `portfolio/`). Rebase onto `origin/<base>` before opening the PR.

## License record (epic acceptance: check recorded)

| Dependency | License | Verdict |
|---|---|---|
| market-trackers-data dumps | CC0-1.0 | Integrate freely; keep `provenance.sourceUrl` |
| edge-stats code (`stats.ts`) | MIT © 2026 LuxAlgo Global, LLC | Port freely; do not vendor `data/` (CC BY); do not rebrand (TRADEMARKS.md) |
| `@luxalgo/broker-sdk@0.5.1` | MIT | Mirror shapes in Python; keys local-only |
| `@luxalgo/vela@0.8.0` | Apache-2.0 | Embed allowed; ship LICENSE + NOTICE; keep watermark or equivalent attribution |
| `@luxalgo/journal-core@0.1.0` | MIT (assumed per family; unstable API) | Learn patterns only; do not depend |
| `@luxalgo/vela-pinets`, PineTS, pinets-cli | AGPL-3.0 | Excluded from all workstreams |

---

### Workstream A: CC0 congress-trades ingest into digisearch (#4826)

**Files:**
- Create: `digisearch/src/digisearch/trackers_ingest.py` (fetch + normalize + ingest entry point)
- Create: `tests/ds/test_trackers_ingest.py` (mocked transport, golden rows)
- Modify: `digisearch/ARCHITECTURE.md` (new adapter path)
- Consumes: `research_ingest.ingest_research_payload` pattern, `pipeline/ingest.index_chunks`, digifetch `HttpFetcher` + `validate_fetch_url`, `core/evidence_metadata.provenance_metadata_from_document`
- Produces: repeatable per-dataset adapter pattern for the remaining 17 datasets

**Interfaces:**
- `fetch_congress_trades_latest(fetcher) -> list[dict]` — GET `https://raw.githubusercontent.com/LuxAlgo/market-trackers-data/main/congress/trades/latest.json`, returns raw row dicts.
- `normalize_congress_trade(row: dict) -> dict` — maps LuxAlgo fields to `{doc_id, text, metadata}` where `doc_id = f"{chamber}:{docId}:{rowIndex}"`, `metadata = {source_url: provenance.sourceUrl, ticker, side, amount_text, transacted_at, needs_review, origin: "luxalgo-trackers/congress-trades"}`. Null ticker → `ticker: None`, still ingested.
- `ingest_congress_trades(fetcher=None) -> IngestResult` — fetch → normalize → `index_chunks`; returns `{ingested: int, skipped: int, source: "luxalgo-trackers/congress-trades"}`.

- [ ] **Step 1: Write the failing test.** Create `tests/ds/test_trackers_ingest.py` with two golden rows copied from the live schema (one stock with ticker, one null-ticker bond), a fake fetcher returning them, and assertions: `ingest_congress_trades(fake)` returns `ingested == 2`; re-ingest returns `ingested == 0` (idempotent); every stored chunk metadata contains the exact upstream `source_url`. Look at `tests/ds/test_research_ingest.py` and `test_chroma_idempotent_ingest.py` for the idempotency assertion style first.
- [ ] **Step 2: Run it to verify it fails.** Run: `pytest tests/ds/test_trackers_ingest.py -v`. Expected: FAIL with `ModuleNotFoundError: No module named 'digisearch.trackers_ingest'` (or ImportError on the entry point).
- [ ] **Step 3: Write minimal implementation.** Create `digisearch/src/digisearch/trackers_ingest.py` with the three functions above. Fetch via digifetch `HttpFetcher` (see `pipeline/url_ingest.py:108` for the allowed pattern). Deterministic ids via the existing `_stable_doc_id`-style helper in `research_ingest.py:141` — import and reuse it, do not duplicate it. At implement time, re-fetch `manifest.json` and refuse to ingest any dataset flagged `stale: true`.
- [ ] **Step 4: Run tests to verify they pass.** Run: `pytest tests/ds/test_trackers_ingest.py tests/ds/test_research_ingest.py -m unit -v`. Expected: PASS, no live HTTP (prove by disconnecting network or asserting fake fetcher call count).
- [ ] **Step 5: Docs + commit.** Update `digisearch/ARCHITECTURE.md` (adapter path + dataset expansion order, runner-up `insider-transactions`). Run `ruff check digisearch/ && ruff format digisearch/`. Commit: `feat(digisearch): ingest luxalgo congress-trades CC0 dump (#4826)`.

---

### Workstream B: Honesty envelope for digiquant tearsheets (#4828)

**Files:**
- Create: `digiquant/src/digiquant/stats/honesty.py` + `digiquant/src/digiquant/stats/__init__.py`
- Create: `tests/dq/test_honesty.py`
- Modify: `digiquant/src/digiquant/tearsheet_stats.py:76`, `:145` (join N); `tearsheet_page.py:49`, `:74-76`; `charts/trades.py:205`; `scripts/generate_tearsheets.py:1050`; `tearsheet_data.py` (`StatBlock` + payload)
- Modify: `digiquant/ARCHITECTURE.md`
- Consumes: upstream `packages/core/src/stats/stats.ts` (port source; pull `stats.test.ts` golden vectors at implement time), `tearsheet.py:130` (`result.num_trades`)
- Produces: `HonestRate` contract reused by any future stats surface

**Interfaces:**
- `wilson(k: int, n: int, z: float = 1.959963984540054) -> Wilson | None` (`Wilson = {estimate, lo, hi}`; `None` when `n == 0`), stdlib `math` only.
- `apply_guards(n: int, *, warn: int = 30, refuse: int = 10) -> GuardResult` (`{low_sample: bool, refused: bool}`).
- `stability_split(n1, k1, n2, k2) -> StabilitySplit` (`agree` = Wilson CI overlap, `None` when either half empty).
- `DISCLAIMER: str = "Historical conditional frequencies with sample sizes. Not predictions, not advice."`
- `format_honest_rate(k, n) -> str` — shape `"{pct:.1f}% (k/n, 95% CI [lo, hi])"`, `"REFUSED — n < 10"` below floor, `"LOW SAMPLE"` below warn. Never emits a bare `%`.

- [ ] **Step 1: Write the failing test.** Create `tests/dq/test_honesty.py`: port cases from upstream `packages/core/test/stats.test.ts` (fetch the file at implement time; at minimum pin `wilson(7, 10)` estimate/lo/hi to 4 decimals, `apply_guards(9).refused is True`, `apply_guards(20).low_sample is True`, `apply_guards(50)` clean, a stability agree + disagree pair, and `format_honest_rate` containing `n=` and `CI`). African grey rule: every assertion names N.
- [ ] **Step 2: Run it to verify it fails.** Run: `pytest tests/dq/test_honesty.py -v`. Expected: FAIL with `ModuleNotFoundError`.
- [ ] **Step 3: Write minimal implementation.** Create `stats/honesty.py` (stdlib `math` only — Wilson is ~10 lines; do not add scipy). Port, do not transliterate blindly: keep names and floors identical (`warn=30`, `refuse=10`) so vectors match.
- [ ] **Step 4: Run tests.** Run: `pytest tests/dq/test_honesty.py -m unit -v`. Expected: PASS.
- [ ] **Step 5: Thread through tearsheets (one surface per commit).** In order: (a) `tearsheet_stats.py:76` + `:145` — pass `num_trades` into the row builder and render via `format_honest_rate`; (b) `tearsheet_page.py:49` KPI strip + move `:74-76` thresholds to act on CI lower bound, not the point estimate; (c) `charts/trades.py:205` donut — stop reconstructing wins via `round()`, take `(k, n)` from the caller; (d) `generate_tearsheets.py:1050` log line to the `renderResult` shape; (e) `tearsheet_data.py` — add `win_rate_ci95` + `win_rate_n` to `StatBlock`/payload (check `BacktestResult` versioning rule in `digiquant/AGENTS.md` first; bump only if the rule says so). After each, run the matching test file (`test_tearsheet_data.py`, `test_mcp_tearsheet_tool.py`, `strategies/sdca/test_tearsheet_charts.py`) plus new assertions that the rendered output contains `n=` and `CI`.
- [ ] **Step 6: Docs + commit(s).** Update `digiquant/ARCHITECTURE.md`; record upstream commit pinned for vectors + MIT check on #4828. Ruff clean. One commit per surface, e.g. `feat(digiquant): honest win-rate in tearsheet stats (#4828)`.

---

### Workstream C: Broker-SDK read-only Alpaca golden path (#4829)

**Files:**
- Create: `digiquant/src/digiquant/brokers/luxalgo_mirror.py` (pure normalization, no I/O)
- Create: `tests/dq/brokers/test_luxalgo_mirror.py` (golden vector, mocked)
- Modify (small, read-only): one consumer — either briefing enrichment near `research/segments.py:583` or reconciliation vs `broker_position_snapshots` (choose at implement time, say which in the PR)
- Consumes: `brokers/contracts.py` (`BrokerAccountSnapshot`, `BrokerPosition`, `BrokerFill`), SDK `BrokerSnapshot/Account/Position/Trade` shapes (mirrored, not imported — SDK is TypeScript)
- Produces: `snapshot_to_contracts()` mapping + golden-vector test pattern for future brokers

**Interfaces:**
- `snapshot_to_contracts(snapshot: dict) -> tuple[BrokerAccountSnapshot, list[BrokerPosition], list[BrokerFill]]` — pure function. Converts JS floats to `Decimal` via `Decimal(str(x))` (never float-through), timestamps to UTC datetimes, signed quantities preserved, currency passed through untouched (caller normalizes via `./fx` later — out of scope).
- `summarize_mirror(accounts) -> dict` — equity-by-account + position count for the briefing payload (mirrors SDK `computeStats` minimally; no trade-stats port in this issue).

- [ ] **Step 1: Write the failing test.** Create `tests/dq/brokers/test_luxalgo_mirror.py` with a golden vector: canned Alpaca-style `BrokerSnapshot` dict (2 accounts, mixed currencies, one short position, 3 trades incl. one with missing `executedAt`) asserting exact `Decimal` equity/quantity values, UTC `as_of`, signed short quantity, and `trades` → `BrokerFill` mapping with `[]` preserved when the broker exposes no window. Model the file header on `test_alpaca_adapter.py:1-7` (`pytestmark = pytest.mark.unit`, mocked, no network).
- [ ] **Step 2: Run it to verify it fails.** Run: `pytest tests/dq/brokers/test_luxalgo_mirror.py -v`. Expected: FAIL with `ModuleNotFoundError`.
- [ ] **Step 3: Write minimal implementation.** Create `brokers/luxalgo_mirror.py` with the two functions. No imports from any SDK package (it is TypeScript); no HTTP; no credential handling in this module. Document in the module docstring: keys stay local, snapshots are caller-persisted, JS-number precision caveat.
- [ ] **Step 4: Run tests.** Run: `pytest tests/dq/brokers/ -m unit -v`. Expected: PASS, existing Alpaca/IBKR adapter untouched and green.
- [ ] **Step 5: Wire one read consumer.** Either (a) enrich briefing context adjacent to `digest_briefing_for_portfolio` (`research/segments.py:583`) with `summarize_mirror` output, or (b) reconcile mirror output against `broker_position_snapshots` rows. Do exactly one; never write into `positions` (H9 owns it). Cover with a test using canned snapshots.
- [ ] **Step 6: Docs + draft PR.** Record SDK version + MIT check + credential-locality notes on #4829. Ruff clean. Open draft PR against `module/digiquant`, body notes **human review required before merge (brokers/ gate)** and that the experimental `orders` module was not touched.

---

### Workstream D: Vela read-only spike in dashboard (#4830)

**Files:**
- Create: spike route/component under `apps/dashboard/` rendering headless `Vela` from digiquant-owned bars (exact path per dashboard conventions — check `apps/dashboard` layout at implement time)
- Create: colocated test asserting render with canned bars + attribution presence
- Create: `apps/dashboard/NOTICE.luxalgo-vela` (copy of upstream NOTICE) + LICENSE attribution entry
- Consumes: `npm i @luxalgo/vela@0.8.0`, dashboard bar endpoint or canned JSON
- Produces: embed-vs-link decision record on #4830

**Interfaces:**
- Spike component props: `{bars: Bar[], symbol: string}` where `Bar = {t, o, h, l, c, v}` from digiquant-owned data only (keyless crypto provider or offline `data` option acceptable for the spike).
- Attribution element: visible "Chart by Vela (LuxAlgo) <link>" on the same screen (satisfies the `attribution:false` condition) — assert its presence in the test.

- [ ] **Step 1: Spike the render.** Install `@luxalgo/vela@0.8.0` (exact pin). Render headless `new Vela(el, {symbol, timeframe, data: cannedBars})` on a clearly-marked experimental route. No `@luxalgo/vela-pinets` in the tree — verify with `npm ls` and fail the spike if it appears.
- [ ] **Step 2: Test.** Colocated test: renders with canned bars, shows attribution element, no network calls to LuxAlgo SaaS (mock fetch, assert zero SaaS calls).
- [ ] **Step 3: Compliance.** Ship NOTICE copy + LICENSE entry; screenshot or DOM assertion proving the watermark-or-equivalent is visible.
- [ ] **Step 4: Decision record.** Post on #4830: embed vs QuantCharts deep-link/iframe (close the framing-policy unknown first: check X-Frame-Options/CSP), with cost triggers ($1,199/dev/yr watermark-free; $20k Business OEM). Draft PR against `develop`.

---

## Deferred (not in this phase)

- P2 whale-options / trade-relay / Ultimate seat / prop-firm-sim / OEM charts — explicitly out unless product asks.
- P1-6 PineTS commercial-vs-AGPL — Chris legal decision (§8 Q1); no agent work until decided. Default stands: Pine runs in LuxAlgo.
- twelve-x dashboard hardening (warn@30, halves-agree, recency-diverges) + levels outcome query — follow-up issue after B lands; the grader lives in `digithings-ai/twelve-x` (separate repo).
- Insider-transactions + remaining 16 tracker datasets — follow-up issues after A proves the pattern.
- Non-Alpaca brokers — demand prioritization is a Chris decision (§8 Q2); supply-side gap table is on #4829.

## Self-review

- Spec coverage: P0-2 → A; P0-3 → B; P1-4 → C (+P1-7 journal patterns folded into C as learn inputs); P1-5 → D; P1-6 → Deferred (decision gate); P2 → Deferred. §7 non-goals each map to a Global Constraint. Epic acceptance (child issues ✓, license record ✓ above, no broker secrets ✓, Refs-not-Fixes ✓) satisfied.
- Placeholder scan: all file paths, function names, URLs, versions, and test commands are real (verified 2026-09-30). Remaining unknowns are explicit spike-first steps inside tasks A (manifest staleness re-check, Parquet), B (upstream vector pull, schema-bump rule), D (framing policy).
- Type consistency: `doc_id`/`source_url`/`needs_review` naming matches digisearch `evidence_metadata` canonical keys; `HonestRate`/`Wilson`/`GuardResult` match upstream `stats.ts` names; mirror output types are the existing `brokers/contracts.py` classes.
