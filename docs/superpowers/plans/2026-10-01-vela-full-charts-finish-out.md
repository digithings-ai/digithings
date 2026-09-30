# Vela Full Charts Finish-Out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the Vela chart arc: ship a keyless digiquant bars endpoint (#4880), wire the dashboard Vela chart to it replacing the canned fixture (#4879), and close out both issues plus note epic #4779.

**Architecture:** digiquant gains a read-only `GET /v1/bars?symbol=&timeframe=&limit=` route on the existing `v1` APIRouter, served from the in-process keyless market-data path with a Pydantic response contract; the dashboard `vela-spike` route becomes a server component that fetches those bars (symbol/timeframe from URL search params) and hands them to the unchanged offline-`data` Vela embed. No provider keys, no Pine/scripting, watermark and LICENSE/NOTICE untouched.

**Tech Stack:** FastAPI + Pydantic v2 (digiquant), Next.js App Router + Vitest + happy-dom (apps/dashboard), `@luxalgo/vela` 0.8.0 offline `data` option.

**Spec:** Issues #4879 ([agent] Vela full-chart data wiring) and #4880 ([agent] digiquant keyless bars endpoint for dashboard charts); follow-up to merged PR #4832 (spike) and issue #4830; epic #4779 (LuxAlgo platform + OSS).

## Live state (verified 2026-10-01 via gh, not trusted from handoff)

- `gh pr view 4832 --json state,mergedAt` → **MERGED** to `develop`, merge commit `c581ce806`, merged 2026-09-30T22:53:58Z. Confirmed.
- **SURPRISE 1 — no #4880 implementation PR exists.** `gh pr list --state all` (40 most recent) shows no bars-endpoint PR; `git branch -r | grep -E "488|4879|vela|bars"` shows only the old merged `origin/task/4830-luxalgo-p1--vela-read-only-research-char`. The handoff's "endpoint implementation running with base module/digiquant" is **false** — Task 1 below starts the endpoint from scratch on `module/digiquant`.
- **SURPRISE 2 — both issues have zero comments** (`gh issue view 4879/4880 --comments` empty). No in-progress notes to preserve.
- **SURPRISE 3 — the referenced prior plan `docs/superpowers/plans/2026-09-30-luxalgo-epic-phase.md` does not exist** in the repo; `ls docs/superpowers/plans/ | grep -i -E "luxalgo|vela"` is empty. Recently written plans sit as **uncommitted** files in `docs/superpowers/plans/`; the last committed plans landed in bulk via PR #4306. This plan is therefore committed on its own `docs/` branch (see Task 0) so it does not rot as an untracked file.
- Epic #4779 (`epic(digiquant): LuxAlgo platform + OSS`) is OPEN.
- `scripts/project_routing.json` branches map: `component:digiquant` → `module/digiquant` (two-hop via module branch); `component:website` → `develop` directly (one-hop). #4879 is `component:website`, #4880 is `component:digiquant` — confirmed from issue labels.

## Global Constraints

- Digi product/module names are always lowercase in prose, docs, commits, PR text (`digithings`, `digiquant`, `digichat`, `digivault`, …); code identifiers keep their language casing (`VelaSpikeChart`, `VELA_PROJECT_URL`).
- No Pine, no scripting engines, no AGPL-licensed code anywhere in the diff; `@luxalgo/vela` stays at pinned `0.8.0` via the offline `data` option only.
- Watermark or equivalent visible attribution on every chart screen: keep the default Vela watermark enabled AND the `data-testid="vela-attribution"` block linking `VELA_PROJECT_URL`, plus `LICENSE.luxalgo-vela` / `NOTICE.luxalgo-vela` files intact.
- Keyless offline data only: no provider API keys, no keyed data vendors, no live-network calls in tests (mock all transports; `fetch` mocked to reject in dashboard tests).
- Presentation-only frontend stays on one branch: all #4879 dashboard work on a single task branch off `develop`, one PR.
- Review coverage (docs/agents/CODE_REVIEW_POLICY.md hatch) before every merge: fresh-context `/review <N>`, findings comment opening with `<!-- in-session-review -->`, `reviewed:agent` label; Bugbot `neutral` is not a review.
- `Refs #NNNN` — never `Fixes #NNNN` — in agent PR bodies (automation closes; humans verify).
- Never touch live-trading paths without explicit human approval (not expected here; stop and ask if the data source leads there).

---

### Task 0: Land this plan file

**Files:**
- Create: `docs/superpowers/plans/2026-10-01-vela-full-charts-finish-out.md` (this file)

**Interfaces:**
- Consumes: nothing
- Produces: the committed plan this task list executes

- [ ] **Step 1: Create a docs branch from current develop**

Run:
```bash
git fetch origin develop
git checkout -b docs/vela-full-charts-finish-out-plan origin/develop
```

- [ ] **Step 2: Add and commit this plan file**

Run:
```bash
git add docs/superpowers/plans/2026-10-01-vela-full-charts-finish-out.md
git commit -m "docs(plans): vela full-charts finish-out (#4879/#4880)

Refs #4879, Refs #4880"
git push -u origin docs/vela-full-charts-finish-out-plan
```

- [ ] **Step 3: Open a docs PR with base develop (one-hop, component:root)**

Run:
```bash
gh pr create --base develop --title "docs(plans): vela full-charts finish-out plan" --body "Plan for #4879 + #4880. Refs #4879, Refs #4880"
```

---

### Task 1: Decide the keyless bar source for `GET /v1/bars` (read-only recon, no code)

**Files:**
- Read: `digiquant/src/digiquant/service.py` (existing `service_*` functions — insertion point)
- Read: `digiquant/src/digiquant/server.py:748-770` (`digifetch_*` in-process dispatcher branch)
- Read: `digikey/integrations/service_middleware.py` (`digiquant_path_scopes` — how to exempt a read-only path)

**Interfaces:**
- Consumes: nothing
- Produces: a source decision + auth decision recorded in the Task 2 PR body

- [ ] **Step 1: Identify the keyless fetch function**

Run:
```bash
git checkout module/digiquant
grep -rn "def .*bars\|def .*ohlcv\|def .*klines" digiquant/src/digiquant/data/ digifetch/src/ 2>/dev/null | head -20
grep -rn "build_digifetch_tool_dispatcher" digiquant/src/digiquant/ | head -5
```

Pick the first available keyless source in this order: (a) the `digifetch_*` in-process dispatcher already called at `server.py:760` (`build_digifetch_tool_dispatcher()(tool, args)` — Yahoo-backed, browser-like headers per #4878, no keys); (b) a `GloomberbClient` method under `digiquant/src/digiquant/data/gloomberb/`; (c) the read-only Coinbase mirror at `digiquant/src/digiquant/brokers/luxalgo_coinbase_mirror.py`. Record the pick (function name + module) in the Task 2 PR body. Do not wrap a live-trading or order path — if every candidate leads to one, stop and ask.

- [ ] **Step 2: Decide auth-exemption for the new route**

`digiquant/ARCHITECTURE.md` §3 states every endpoint except `/health` requires a digikey JWT, but the dashboard is a presentation-only server component and issue #4880 specifies "keyless … no auth/credential surface". Read `digiquant_path_scopes` in `digikey/integrations/service_middleware.py` and check how `/healthz` (`server.py:220`) stays auth-exempt. Recommended: register `GET /v1/bars` as auth-exempt read-only (same mechanism as `/healthz`) because it serves public market bars with no user data and no write surface. If exemption is not possible without touching auth/crypto paths, stop and ask (auth changes need a human per the human gate) and fall back to dashboard-side digikey exchange.

---

### Task 2: Pydantic bars contract + `service_get_bars` (module/digiquant branch)

**Files:**
- Modify: `digiquant/src/digiquant/models.py` (add `Bar` + `BarsResponse` — check current exports first)
- Modify: `digiquant/src/digiquant/service.py` (add `service_get_bars`)
- Test: `tests/dq/test_bars.py` (new; mirrors `tests/dq/test_api.py` TestClient pattern)

**Interfaces:**
- Consumes: source function picked in Task 1 (exact module + function name)
- Produces: `Bar(t: int, o: float, h: float, l: float, c: float, v: float | None)`, `BarsResponse(symbol: str, timeframe: str, bars: list[Bar])`, `service_get_bars(symbol: str, timeframe: str, limit: int) -> BarsResponse`

- [ ] **Step 1: Create the task branch from current module/digiquant**

Run:
```bash
git fetch origin
git checkout -b task/4880-digiquant-keyless-bars-endpoint origin/module/digiquant
```

- [ ] **Step 2: Write the failing contract test**

Create `tests/dq/test_bars.py`:
```python
"""Unit tests for the keyless bars endpoint (issue #4880). Transport always mocked."""

from __future__ import annotations

from unittest.mock import patch

from digiquant.models import Bar, BarsResponse
from digiquant.server import app
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers


def _client() -> TestClient:
    return TestClient(app, headers=auth_headers())


def test_bars_response_contract() -> None:
    bars = BarsResponse(
        symbol="BTCUSDT",
        timeframe="1D",
        bars=[Bar(t=1727740800000, o=100.0, h=104.0, l=99.0, c=103.0, v=1200.0)],
    )
    assert bars.bars[0].c == 103.0
    assert bars.symbol == "BTCUSDT"


def test_get_bars_returns_mocked_bars() -> None:
    fake = {
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "bars": [
            {"t": 1727740800000, "o": 100.0, "h": 104.0, "l": 99.0, "c": 103.0, "v": 1200.0},
            {"t": 1727827200000, "o": 103.0, "h": 107.0, "l": 102.0, "c": 106.0, "v": 1500.0},
        ],
    }
    with patch("digiquant.service.service_get_bars") as mock_service:
        from digiquant.models import BarsResponse as BR

        mock_service.return_value = BR.model_validate(fake)
        resp = _client().get("/v1/bars", params={"symbol": "BTCUSDT", "timeframe": "1D", "limit": 2})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["symbol"] == "BTCUSDT"
    assert payload["timeframe"] == "1D"
    assert len(payload["bars"]) == 2
    assert set(payload["bars"][0]) >= {"t", "o", "h", "l", "c"}
    mock_service.assert_called_once_with(symbol="BTCUSDT", timeframe="1D", limit=2)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/dq/test_bars.py -v`
Expected: FAIL (`Bar` / `BarsResponse` not defined, `/v1/bars` 404).

- [ ] **Step 4: Add the Pydantic contract to models.py**

Append to `digiquant/src/digiquant/models.py` (Pydantic v2, strict typing, ruff line length 100):
```python
class Bar(BaseModel):
    """Single OHLCV bar for the keyless bars endpoint (#4880). `t` is bar open epoch ms."""

    model_config = ConfigDict(strict=True)

    t: int = Field(..., description="Bar open time, epoch milliseconds")
    o: float = Field(..., description="Open price")
    h: float = Field(..., description="High price")
    l: float = Field(..., description="Low price")
    c: float = Field(..., description="Close price")
    v: float | None = Field(default=None, description="Volume (if the source reports it)")


class BarsResponse(BaseModel):
    """Response contract for GET /v1/bars (#4880). Read-only, keyless, no auth surface."""

    model_config = ConfigDict(strict=True)

    symbol: str = Field(..., description="Normalized symbol, e.g. BTCUSDT")
    timeframe: str = Field(..., description="Bar timeframe, e.g. 1D, 1h")
    bars: list[Bar] = Field(default_factory=list, description="Oldest-first OHLCV bars")
```

If `models.py` already sets a shared `model_config` convention, match it instead of adding `ConfigDict(strict=True)` per-model — check the file first.

- [ ] **Step 5: Add `service_get_bars` to service.py**

Place next to `service_list_strategies` in `digiquant/src/digiquant/service.py`:
```python
def service_get_bars(symbol: str, timeframe: str = "1D", limit: int = 30) -> BarsResponse:
    """Fetch recent OHLCV bars from the keyless market-data path (Task 1 pick).

    Read-only: no keys, no orders, no credential surface. Raises ValueError on
    bad symbol/timeframe so the route can return 400/422.
    """
    from digiquant.models import Bar, BarsResponse

    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")
    tf = (timeframe or "1D").strip()
    n = max(1, min(int(limit), 500))
    raw_bars = _fetch_keyless_bars(sym, tf, n)  # Task 1 pick goes here
    return BarsResponse(
        symbol=sym,
        timeframe=tf,
        bars=[
            Bar(t=int(b["t"]), o=float(b["o"]), h=float(b["h"]),
                l=float(b["l"]), c=float(b["c"]),
                v=None if b.get("v") is None else float(b["v"]))
            for b in raw_bars
        ],
    )
```

Replace `_fetch_keyless_bars(sym, tf, n)` with the real Task 1 call (exact module + function name, e.g. the digifetch dispatcher or `GloomberbClient` method). The service layer does the `dict` → `Bar` normalization so the route stays thin. Never call live HTTP at import time; tests patch `digiquant.service.service_get_bars`.

- [ ] **Step 6: Run the contract + service tests**

Run: `.venv/bin/python -m pytest tests/dq/test_bars.py -v`
Expected: contract test PASSES; endpoint test still FAILS (404 — route comes in Task 3). If the endpoint test unexpectedly passes, the route already exists — re-check `server.py` for a duplicate.

- [ ] **Step 7: Commit**

```bash
git add digiquant/src/digiquant/models.py digiquant/src/digiquant/service.py tests/dq/test_bars.py
git commit -m "feat(digiquant): bars Pydantic contract + service_get_bars

Refs #4880"
```

---

### Task 3: `GET /v1/bars` route + ARCHITECTURE.md (same branch)

**Files:**
- Modify: `digiquant/src/digiquant/server.py` (route on `v1` APIRouter defined at line 358, included at line 1113; rate-limit map `_RATE_LIMITS` at lines 66-72)
- Modify: `digiquant/ARCHITECTURE.md` (§3 "REST Endpoints" table ~line 148 + "Rate Limits" table ~line 206)
- Test: `tests/dq/test_bars.py` (extend: validation + limit clamp)

**Interfaces:**
- Consumes: `service_get_bars(symbol, timeframe, limit) -> BarsResponse` from Task 2
- Produces: `GET /v1/bars?symbol=&timeframe=1D&limit=30` → `BarsResponse` JSON; 400 on empty symbol

- [ ] **Step 1: Write the failing route tests (append to tests/dq/test_bars.py)**

```python
def test_get_bars_rejects_empty_symbol() -> None:
    resp = _client().get("/v1/bars", params={"symbol": "   "})
    assert resp.status_code in (400, 422)


def test_get_bars_clamps_limit() -> None:
    with patch("digiquant.service.service_get_bars") as mock_service:
        from digiquant.models import BarsResponse as BR

        mock_service.return_value = BR(symbol="BTCUSDT", timeframe="1D", bars=[])
        resp = _client().get("/v1/bars", params={"symbol": "BTCUSDT", "limit": 99999})
    assert resp.status_code == 200, resp.text
    _, kwargs = mock_service.call_args
    assert kwargs["limit"] <= 500
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/dq/test_bars.py -v`
Expected: FAIL (404 on `/v1/bars`).

- [ ] **Step 3: Register the route in server.py**

Add after the `/strategies` handler (`api_list_strategies`, ~line 230) so read-only GETs stay together:
```python
@v1.get("/bars", response_model=BarsResponse)
def api_get_bars(symbol: str, timeframe: str = "1D", limit: int = 30) -> BarsResponse:
    """Recent OHLCV bars from the keyless market-data path (#4880).

    Read-only: no keys, no orders, no credential surface. `limit` clamps to [1, 500].
    """
    from digiquant.service import service_get_bars

    try:
        return service_get_bars(symbol=symbol, timeframe=timeframe, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
```

Add `BarsResponse` to the existing `from digiquant.models import (...)` at `server.py:29` (extend that import, do not add a second import). Add a rate-limit entry `"/v1/bars": (30, 60)` to `_RATE_LIMITS` (`server.py:66-72`), matching the read-only `/v1/orchestrator_tools` budget. Apply the Task 1 auth decision: if exemption, use the same mechanism as `/healthz`; otherwise leave default middleware protection and note it in the PR body.

- [ ] **Step 4: Document the endpoint in digiquant/ARCHITECTURE.md**

Add to the §3 synchronous-endpoints table (after the `/v1/workflow` row, ~line 160):
`| GET | /v1/bars | <scope or public per Task 1> | Keyless OHLCV bars (symbol/timeframe/limit, clamped [1, 500]) — #4880 |`
Add to the §3 rate-limits table (~line 206): `| /v1/bars | 30 requests / 60 s |`

- [ ] **Step 5: Run tests + lint**

Run:
```bash
.venv/bin/python -m pytest tests/dq/test_bars.py tests/dq/test_api.py -v
.venv/bin/ruff check digiquant/src/digiquant/server.py digiquant/src/digiquant/service.py digiquant/src/digiquant/models.py tests/dq/test_bars.py
```
Expected: all PASS, ruff clean. (If `make test-unit` SIGABRTs on this Linux host per AGENTS.md caveat #42, the targeted subset above is the gate.)

- [ ] **Step 6: Commit**

```bash
git add digiquant/src/digiquant/server.py digiquant/ARCHITECTURE.md tests/dq/test_bars.py
git commit -m "feat(digiquant): keyless GET /v1/bars endpoint

Refs #4880"
```

---

### Task 4: Review + merge #4880 PR to module/digiquant, promote to develop

**Files:**
- None (review + merge operations)

- [ ] **Step 1: Push and open the PR with base module/digiquant**

Run:
```bash
git push -u origin task/4880-digiquant-keyless-bars-endpoint
gh pr create --base module/digiquant --title "[agent] digiquant keyless bars endpoint for dashboard charts" --body "Keyless GET /v1/bars (symbol/timeframe/limit) from <Task 1 source pick>. Read-only, Pydantic BarsResponse, mocked-transport tests, ARCHITECTURE.md updated. Auth: <Task 1 decision>. Refs #4880"
```

- [ ] **Step 2: Run the review-coverage hatch**

Dispatch a fresh-context subagent `/review <PR>` (scope pass first, deep lens only on flagged areas per CODE_REVIEW_POLICY.md). Post survivors as a PR comment opening with `<!-- in-session-review -->` and apply label `reviewed:agent`. Fix what the review finds on the same branch. Checklist the reviewer must confirm: keyless (no provider keys/credentials in diff), Pydantic contract matches `BarsResponse`, tests mock transport (no live HTTP), ARCHITECTURE.md updated, no live-trading/order paths touched.

- [ ] **Step 3: Merge to module/digiquant when green**

Merge-ready = required CI green + branch not conflicted + review threads triaged + review hatch on record. Then `gh pr merge <N> --squash` (match module-branch convention) into `module/digiquant`.

- [ ] **Step 4: Promote module/digiquant → develop**

Open promotion PR `head=module/digiquant`, `base=develop` (normal PR, no force-push — module branches forbid it). Same merge-ready bar, then merge. `GET /v1/bars` is now live on develop. Do not close #4880 yet (dashboard wiring in Tasks 5-6 proves it end to end).

---

### Task 5: Wire the dashboard Vela route to `GET /v1/bars` (#4879, one branch off develop)

**Files:**
- Modify: `apps/dashboard/app/research/vela-spike/page.tsx` (remove `CANNED_FIXTURE_BARS`, fetch real bars, symbol/timeframe params)
- Modify: `apps/dashboard/components/research/VelaSpikeChart.tsx` (drop `experimental` badge ONLY — keep `VELA_PROJECT_URL`, `VELA_VERSION`, watermark default, `data-testid="vela-attribution"`, `quantChartsHref` deep-link, empty state)
- Test: `apps/dashboard/components/research/VelaSpikeChart.test.tsx` + `.dom.test.tsx` (update badge assertion, add data-path tests)

**Interfaces:**
- Consumes: `GET /v1/bars?symbol=&timeframe=&limit=` → `{symbol, timeframe, bars: [{t,o,h,l,c,v?}]}` (Task 3; field names map 1:1 onto `VelaSpikeBar`)
- Produces: `VelaSpikePage({searchParams: {symbol?, timeframe?}})` rendering `VelaSpikeChart` with live bars

- [ ] **Step 1: Create the single wiring branch from develop**

Run:
```bash
git fetch origin
git checkout -b task/4879-vela-full-chart-data-wiring origin/develop
```

- [ ] **Step 2: Rewrite the route as a fetching server component**

Replace the full contents of `apps/dashboard/app/research/vela-spike/page.tsx` (delete the `CANNED_FIXTURE_BARS` IIFE entirely — no fixture import may remain):
```tsx
import VelaSpikeChart, { type VelaSpikeBar } from '@/components/research/VelaSpikeChart';

const DIGIQUANT_BASE = process.env.DIGIQUANT_BASE_URL ?? 'http://127.0.0.1:8001';
const ALLOWED_TIMEFRAMES = new Set(['15m', '1h', '4h', '1D', '1W']);

interface BarsApiBar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v?: number | null;
}

async function fetchBars(symbol: string, timeframe: string): Promise<VelaSpikeBar[] | { error: string }> {
  let res: Response;
  try {
    res = await fetch(
      `${DIGIQUANT_BASE}/v1/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&limit=120`,
      { cache: 'no-store' }
    );
  } catch (err) {
    return { error: err instanceof Error ? err.message : String(err) };
  }
  if (!res.ok) return { error: `digiquant /v1/bars responded ${res.status}` };
  const payload = (await res.json()) as { bars?: BarsApiBar[] };
  const bars = Array.isArray(payload.bars) ? payload.bars : [];
  return bars.map((b) => ({
    t: b.t,
    o: b.o,
    h: b.h,
    l: b.l,
    c: b.c,
    ...(b.v === undefined || b.v === null ? {} : { v: b.v }),
  }));
}

export default async function VelaSpikePage({
  searchParams,
}: {
  searchParams?: { symbol?: string; timeframe?: string };
}) {
  const symbol = (searchParams?.symbol ?? 'BTCUSDT').toUpperCase().slice(0, 20) || 'BTCUSDT';
  const timeframe = ALLOWED_TIMEFRAMES.has(searchParams?.timeframe ?? '')
    ? (searchParams as { timeframe: string }).timeframe
    : '1D';
  const result = await fetchBars(symbol, timeframe);

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <div className="space-y-1">
        <h1 className="text-lg font-semibold">Vela read-only research chart</h1>
        <p className="font-mono text-[11px] text-ink-mute">
          #4879 · headless Vela core on digiquant-owned bars · read-only · no Pine scripting · no
          SaaS calls
        </p>
      </div>
      {Array.isArray(result) ? (
        <VelaSpikeChart bars={result} symbol={`RESEARCH/${symbol}`} timeframe={timeframe} />
      ) : (
        <div className="border border-hair bg-surface/40 p-4 text-xs text-ink-mute" data-testid="vela-spike-error">
          Could not load bars for {symbol} ({timeframe}): {result.error} — strategy work continues
          in <a href="https://app.luxalgo.com/" target="_blank" rel="noreferrer" className="underline">QuantCharts</a>.
        </div>
      )}
      <p className="font-mono text-[10px] text-ink-mute">
        Bars served keyless by digiquant GET /v1/bars. Compliance: Apache-2.0 LICENSE + Vela
        NOTICE ship with the dashboard (LICENSE.luxalgo-vela, NOTICE.luxalgo-vela); attribution
        stays visible on this screen.
      </p>
    </main>
  );
}
```

Keep: the `RESEARCH/` symbol prefix convention, the QuantCharts deep-link (both in-chart `quantChartsHref` default and the error-state link), the compliance footer naming both license files. Drop: the word "experimental" everywhere on this route, the canned-fixture paragraph. Verify `LICENSE.luxalgo-vela` exists next to `NOTICE.luxalgo-vela` in `apps/dashboard/` — if the LICENSE file is missing, create it from the Vela Apache-2.0 text rather than editing the footer copy.

- [ ] **Step 3: Drop the experimental badge in VelaSpikeChart.tsx (only that)**

In `apps/dashboard/components/research/VelaSpikeChart.tsx`, replace:
```tsx
        {' · '}
        <span className="rounded border border-hair px-1 text-ink-mute">experimental</span>
```
with nothing (delete both lines). Do not touch the `Vela` constructor args (`data`, `timeframe`, `theme: 'dark'`, `live: false`, `drawings: false`), the attribution block, the empty state, or the mount-error path.

- [ ] **Step 4: Update the chart tests — badge out, data-path in**

In `VelaSpikeChart.test.tsx`, change the first test to assert the badge is gone:
```tsx
  it('renders the symbol caption with bar count and range and no experimental badge', () => {
    const html = renderToStaticMarkup(
      createElement(VelaSpikeChart, { bars: BARS, symbol: 'BTCUSDT', timeframe: '1D' })
    );
    expect(html).toContain('data-testid="vela-spike-chart"');
    expect(html).toContain('BTCUSDT');
    expect(html).toContain('3 bars');
    expect(html).not.toContain('experimental');
    expect(html).toContain('data-testid="vela-spike-host"');
  });
```

In `VelaSpikeChart.dom.test.tsx`, append a data-shape test proving the endpoint payload maps onto the mocked constructor args (endpoint field names → Vela `OHLCV` option keys):
```tsx
  it('maps endpoint bar fields onto the offline OHLCV data shape', async () => {
    await renderAndWaitForMount();

    const [{ options }] = velaMock.instances;
    const data = options.data as Array<Record<string, unknown>>;
    expect(data).toHaveLength(2);
    expect(Object.keys(data[0]).sort()).toEqual(
      ['close', 'high', 'low', 'open', 'time', 'volume']
    );
    expect(data[0]).toMatchObject({ time: 1727740800000, open: 100, close: 103, volume: 1200 });
    // Second bar carries no volume — the key must be absent, not undefined.
    expect(data[1]).toMatchObject({ time: 1727827200000, open: 103, close: 106 });
    expect('volume' in data[1]).toBe(false);
  });
```

- [ ] **Step 5: Run the dashboard suite for the research chart**

Run:
```bash
cd apps/dashboard && npx vitest run components/research/VelaSpikeChart.test.tsx components/research/VelaSpikeChart.dom.test.tsx
```
Expected: all PASS (including the pre-existing mocked-`Vela` constructor-args test asserting `live: false`, `drawings: false`, no provider, no network). `fetch` stays mocked-to-reject in these tests — the component itself never fetches (only the server page does).

- [ ] **Step 6: Smoke the live data path against a local stack**

Run (needs the host-native stack; `lsof` + Python 3.12 venv per AGENTS.md Cursor Cloud notes):
```bash
PATH="$PWD/.venv/bin:$PATH" make stack-local
curl -s "http://127.0.0.1:8001/v1/bars?symbol=BTCUSDT&timeframe=1D&limit=5" | head -c 600
```
Expected: `{"symbol":"BTCUSDT","timeframe":"1D","bars":[...]}` with real bars. Then open the dashboard route with `?symbol=BTCUSDT&timeframe=1D` and confirm bars render (watermark visible). Stop the stack with `./scripts/stop_stack_local.sh` afterwards.

- [ ] **Step 7: Commit**

```bash
git add apps/dashboard/app/research/vela-spike/page.tsx apps/dashboard/components/research/VelaSpikeChart.tsx apps/dashboard/components/research/VelaSpikeChart.test.tsx apps/dashboard/components/research/VelaSpikeChart.dom.test.tsx
git commit -m "feat(dashboard): wire vela chart to digiquant bars endpoint

Refs #4879, Refs #4880"
```

---

### Task 6: Review + merge wiring PR, close issues, note epic

**Files:**
- None (review + merge + issue hygiene)

- [ ] **Step 1: Push and open the wiring PR with base develop**

Run:
```bash
git push -u origin task/4879-vela-full-chart-data-wiring
gh pr create --base develop --title "[agent] Vela full-chart data wiring (post-spike)" --body "Replaces CANNED_FIXTURE_BARS with digiquant GET /v1/bars (symbol/timeframe route params, loading/empty/error states). Experimental badge dropped; QuantCharts deep-link, watermark, LICENSE/NOTICE kept. Data-path tests mock @luxalgo/vela and assert constructor args. Refs #4879, Refs #4880"
```

- [ ] **Step 2: Run the review-coverage hatch**

Fresh-context subagent `/review <PR>`; post survivors opening with `<!-- in-session-review -->`; apply `reviewed:agent`. Fix findings on the branch. Reviewer confirms: no fixture import remains, badge gone, deep-link + attribution intact, no Pine/scripting, no keyed provider, `fetch` confined to the server page.

- [ ] **Step 3: Merge to develop when merge-ready, then close the loop**

`gh pr merge <N>` into `develop` (match base convention). Then:
```bash
gh issue close 4879 --comment "Wired in <PR#> — live bars via GET /v1/bars, badge dropped, deep-link + attribution kept."
gh issue close 4880 --comment "Endpoint shipped in <PR#> (module/digiquant, promoted to develop) and proven by the dashboard wiring in <wiring-PR#>."
gh issue comment 4779 --body "Vela full-charts finish-out landed: keyless GET /v1/bars (#4880) + dashboard wiring (#4879, post-spike follow-up to #4832). Watermark + LICENSE/NOTICE intact; no Pine/scripting."
```

---

## Self-review

1. **Spec coverage:** #4880 acceptance criteria → Task 2 (contract + service + mocked-transport tests), Task 3 (route + ARCHITECTURE.md + rate limit), Task 4 (merge + promote). #4879 criteria → Task 5 (real bars via offline `data`, fixture removed, symbol/timeframe params, badge removed, deep-link kept, mocked-Vela constructor-args + data-path tests, suite green, watermark + LICENSE/NOTICE intact, no Pine/scripting). Epic #4779 note → Task 6 Step 3. Docs touches (`ARCHITECTURE.md` for #4880; route/component touched for #4879) are explicit steps. No gaps.
2. **Placeholder scan:** No TBD/TODO/"implement later". The one deliberate deferral — the Task 1 source pick — is a bounded recon task producing an exact function name consumed by Task 2's `Interfaces` block, with an ordered candidate list and file:line pointers, not an open blank. Error states are specified inline (400/422, error div with deep-link fallback). Edge cases named concretely (empty symbol, limit clamp to 500, missing volume key, missing LICENSE file).
3. **Type consistency:** `Bar`/`BarsResponse` field names (`t,o,h,l,c,v`) match the endpoint JSON, the page's `BarsApiBar`, `VelaSpikeBar`, and the dom-test's expected Vela option keys (`time,open,high,low,close,volume`) with the `v`→`volume` omission rule repeated verbatim in both page and test. `service_get_bars(symbol, timeframe, limit)` signature matches the test's `assert_called_once_with`. Route path `/v1/bars` + rate-limit key agree. Branch names follow taxonomy (`task/<N>-slug`, `docs/<slug>`); bases follow `project_routing.json` (digiquant→`module/digiquant`, website→`develop`).
