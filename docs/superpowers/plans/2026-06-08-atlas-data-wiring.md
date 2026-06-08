# Atlas Data Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Atlas research phases produce substantive output by grounding the LLM on real data — via a DigiQuant data tool over Supabase (price/technicals/macro) and Grok Live Search (curated domains) — instead of the current freshness-snapshot-only context.

**Architecture:** Equip `run_research_agent` with tools. (1) An in-process + MCP "data tool" reads the `price_technicals`/`macro_series_observations` tables we already maintain. (2) Grok Live Search is enabled per call via `search_parameters` passed through the OpenAI-compatible client's `extra_body`, scoped to a checked-in domain allowlist. Phases run a tool loop (`chat_completion_with_tools`) then validate the final JSON against the Pydantic schema using the existing retry loop (function-tools and `response_format=json_schema` are mutually exclusive; Live Search is orthogonal).

**Tech Stack:** Python 3.12, Polars-free here (plain dicts/JSON), Pydantic v2, Supabase Python client, FastMCP, xAI Grok via OpenAI-compatible client, pytest (`-m unit`).

**Spec:** `docs/superpowers/specs/2026-06-08-atlas-data-wiring-design.md`

---

## File Structure

| Path | Responsibility |
|---|---|
| `digiquant/src/digiquant/olympus/atlas/data/__init__.py` | New `data` subpackage. |
| `digiquant/src/digiquant/olympus/atlas/data/queries.py` | Pure Supabase value queries: `get_price_technicals(...)`, `get_macro_series(...)`. |
| `digiquant/src/digiquant/olympus/atlas/data/tools.py` | In-process `ToolDefinition`s + `build_data_tool_dispatcher(client)` for the research agent loop. |
| `digiquant/src/digiquant/olympus/atlas/data/live_search.py` | `build_search_parameters(run_date, ...)` from the domain allowlist. |
| `digiquant/src/digiquant/olympus/atlas/config/search_domains.yaml` | Curated web-search domain allowlist. |
| `digigraph/src/digigraph/llm.py` | Thread `search_parameters` → `extra_body` (xAI-only) in `chat_completion` + `chat_completion_with_tools`. |
| `digigraph/src/digigraph/graph/research_agent.py` | Tool-loop + validate-retry; new `tools`/`execute_tool`/`search_parameters` params; prompt update. |
| `digiquant/src/digiquant/olympus/atlas/phases/_node_factory.py` | Build data tool + search params per spec flags; pass to `run_research_agent`. |
| `digiquant/src/digiquant/olympus/atlas/phases/*.py` (specs) | Set `use_data_tools` / `live_search` flags per phase. |
| `digiquant/src/digiquant/mcp_server.py` | Register the two queries as MCP tools. |
| `tests/dq/atlas/data/test_queries.py`, `test_tools.py`, `test_live_search.py` | Unit tests for the new data layer. |
| `tests/dg/test_llm_search_params.py`, `tests/dg/test_research_agent_tools.py` | Unit tests for the llm + agent changes. |

> Note on naming: phase output schemas keep optional fields (e.g. `regime_label`, `spy_trend`, `material_findings`). Tools only *supply* data; the schema contract is unchanged.

---

### Task 1: Supabase value-query functions

**Files:**
- Create: `digiquant/src/digiquant/olympus/atlas/data/__init__.py`
- Create: `digiquant/src/digiquant/olympus/atlas/data/queries.py`
- Test: `tests/dq/atlas/data/test_queries.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/atlas/data/test_queries.py
from __future__ import annotations
import pytest
from digiquant.olympus.atlas.data.queries import get_price_technicals, get_macro_series


class _FakeTable:
    def __init__(self, rows): self._rows = rows; self._f = {}
    def select(self, *a, **k): return self
    def eq(self, col, val): self._f[col] = val; return self
    def in_(self, col, vals): self._f[col] = set(vals); return self
    def order(self, *a, **k): return self
    def limit(self, n): self._n = n; return self
    def execute(self):
        rows = [r for r in self._rows
                if all(r.get(c) == v or (isinstance(v, set) and r.get(c) in v) for c, v in self._f.items())]
        return type("R", (), {"data": rows[: getattr(self, "_n", len(rows))]})


class _FakeClient:
    def __init__(self, tables): self._t = tables
    def table(self, name): return _FakeTable(self._t.get(name, []))


@pytest.mark.unit
def test_get_price_technicals_returns_latest_window():
    client = _FakeClient({"price_technicals": [
        {"ticker": "SPY", "date": "2026-06-08", "sma_50": 1.0, "sma_200": 2.0, "rsi_14": 55.0,
         "pct_vs_sma200": 3.1, "macd_hist": 0.2, "adx_14": 21.0, "atr_pct": 1.1, "zscore_200": 0.4},
        {"ticker": "SPY", "date": "2026-06-05", "sma_50": 1.0, "sma_200": 2.0, "rsi_14": 54.0,
         "pct_vs_sma200": 3.0, "macd_hist": 0.1, "adx_14": 20.0, "atr_pct": 1.0, "zscore_200": 0.3},
        {"ticker": "QQQ", "date": "2026-06-08", "sma_50": 9.0, "sma_200": 8.0, "rsi_14": 60.0,
         "pct_vs_sma200": 5.0, "macd_hist": 0.5, "adx_14": 25.0, "atr_pct": 1.5, "zscore_200": 0.9},
    ]})
    out = get_price_technicals(client=client, ticker="SPY", lookback=2)
    assert out["ticker"] == "SPY"
    assert out["latest"]["date"] == "2026-06-08"
    assert out["latest"]["rsi_14"] == 55.0
    assert len(out["window"]) == 2
    assert "sma_200" in out["latest"]


@pytest.mark.unit
def test_get_macro_series_groups_by_series():
    client = _FakeClient({"macro_series_observations": [
        {"series_id": "M2SL", "obs_date": "2026-05-01", "value": 21000.0, "unit": "Bil. $"},
        {"series_id": "M2SL", "obs_date": "2026-04-01", "value": 20950.0, "unit": "Bil. $"},
        {"series_id": "DFF", "obs_date": "2026-06-07", "value": 4.5, "unit": "%"},
    ]})
    out = get_macro_series(client=client, series_ids=["M2SL", "DFF"], lookback=2)
    assert set(out) == {"M2SL", "DFF"}
    assert out["M2SL"]["latest"]["value"] == 21000.0
    assert out["DFF"]["latest"]["value"] == 4.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/atlas/data/test_queries.py -m unit -v`
Expected: FAIL — `ModuleNotFoundError: digiquant.olympus.atlas.data.queries`

- [ ] **Step 3: Create the package init**

```python
# digiquant/src/digiquant/olympus/atlas/data/__init__.py
"""Atlas data-access layer: read maintained Supabase series for agent grounding."""
```

- [ ] **Step 4: Write the implementation**

```python
# digiquant/src/digiquant/olympus/atlas/data/queries.py
"""Read structured price/technical + macro values from Supabase for the research agent.

These return compact, token-budgeted JSON (latest snapshot + a short recent window),
not full history. Selected technical columns only — the model gets signal, not noise.
"""
from __future__ import annotations

from typing import Any

# Indicator columns surfaced to the agent (trend / momentum / regime). Not all 30+.
TECHNICAL_COLUMNS: tuple[str, ...] = (
    "date", "sma_50", "sma_200", "pct_vs_sma50", "pct_vs_sma200",
    "rsi_14", "macd_hist", "roc_21", "adx_14", "atr_pct", "bb_pct_b", "zscore_200",
)


def get_price_technicals(*, client: Any, ticker: str, lookback: int = 20) -> dict[str, Any]:
    """Return {ticker, latest, window[]} of selected technicals for one ticker.

    ``window`` is newest-first, length <= lookback. ``latest`` is window[0] or {}.
    """
    resp = (
        client.table("price_technicals")
        .select(",".join(TECHNICAL_COLUMNS))
        .eq("ticker", ticker)
        .order("date", desc=True)
        .limit(lookback)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    return {"ticker": ticker, "latest": rows[0] if rows else {}, "window": rows}


def get_macro_series(*, client: Any, series_ids: list[str], lookback: int = 6) -> dict[str, Any]:
    """Return {series_id: {latest, window[]}} for each requested FRED series id."""
    out: dict[str, Any] = {}
    for sid in series_ids:
        resp = (
            client.table("macro_series_observations")
            .select("series_id,obs_date,value,unit")
            .eq("series_id", sid)
            .order("obs_date", desc=True)
            .limit(lookback)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        out[sid] = {"latest": rows[0] if rows else {}, "window": rows}
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/dq/atlas/data/test_queries.py -m unit -v`
Expected: PASS (2 passed). Note: the fake's `order(...)` is a no-op, so seed test rows newest-first (as written).

- [ ] **Step 6: Commit**

```bash
git add digiquant/src/digiquant/olympus/atlas/data/__init__.py \
        digiquant/src/digiquant/olympus/atlas/data/queries.py \
        tests/dq/atlas/data/test_queries.py
git commit -m "feat(atlas): Supabase value queries for price-technicals + macro series"
```

---

### Task 2: In-process data tool (ToolDefinitions + dispatcher)

**Files:**
- Create: `digiquant/src/digiquant/olympus/atlas/data/tools.py`
- Test: `tests/dq/atlas/data/test_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/atlas/data/test_tools.py
from __future__ import annotations
import json
import pytest
from digiquant.olympus.atlas.data.tools import DATA_TOOLS, build_data_tool_dispatcher
from tests.dq.atlas.data.test_queries import _FakeClient


@pytest.mark.unit
def test_tool_definitions_shape():
    names = {t["function"]["name"] for t in DATA_TOOLS}
    assert names == {"get_price_technicals", "get_macro_series"}
    for t in DATA_TOOLS:
        assert t["type"] == "function"
        assert "parameters" in t["function"]


@pytest.mark.unit
def test_dispatcher_routes_and_returns_json_string():
    client = _FakeClient({
        "price_technicals": [{"ticker": "SPY", "date": "2026-06-08", "rsi_14": 55.0}],
        "macro_series_observations": [{"series_id": "DFF", "obs_date": "2026-06-07", "value": 4.5}],
    })
    dispatch = build_data_tool_dispatcher(client)
    pt = json.loads(dispatch("get_price_technicals", {"ticker": "SPY", "lookback": 5}))
    assert pt["latest"]["rsi_14"] == 55.0
    mc = json.loads(dispatch("get_macro_series", {"series_ids": ["DFF"], "lookback": 3}))
    assert mc["DFF"]["latest"]["value"] == 4.5
    err = dispatch("nonexistent_tool", {})
    assert "unknown tool" in err.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/atlas/data/test_tools.py -m unit -v`
Expected: FAIL — `ModuleNotFoundError: ...data.tools`

- [ ] **Step 3: Write the implementation**

```python
# digiquant/src/digiquant/olympus/atlas/data/tools.py
"""Expose the Supabase value queries as research-agent function tools.

Two surfaces share the same query functions: these in-process ToolDefinitions
(for chat_completion_with_tools) and the MCP tools in digiquant.mcp_server.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from digiquant.olympus.atlas.data.queries import get_macro_series, get_price_technicals

logger = logging.getLogger(__name__)

DATA_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_price_technicals",
            "description": (
                "Latest technical indicators (sma/rsi/macd/adx/atr/zscore, etc.) plus a "
                "recent daily window for one ticker (e.g. SPY, XLK, TLT). Use to ground "
                "trend, momentum, and relative-strength claims on real data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Ticker symbol, e.g. SPY."},
                    "lookback": {"type": "integer", "description": "Recent trading days (default 20)."},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_macro_series",
            "description": (
                "Latest values + recent window for FRED macro series ids (e.g. M2SL, DFF, "
                "DGS10, T10Y2Y, VIXCLS, DTWEXBGS, T10YIE). Use to ground macro-regime claims."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "series_ids": {"type": "array", "items": {"type": "string"}},
                    "lookback": {"type": "integer", "description": "Recent observations (default 6)."},
                },
                "required": ["series_ids"],
            },
        },
    },
]


def build_data_tool_dispatcher(client: Any) -> Callable[[str, dict[str, Any]], str]:
    """Return an ``execute_tool(name, args) -> json_str`` bound to a Supabase client."""

    def execute_tool(name: str, args: dict[str, Any]) -> str:
        try:
            if name == "get_price_technicals":
                result = get_price_technicals(
                    client=client, ticker=args["ticker"], lookback=int(args.get("lookback", 20))
                )
            elif name == "get_macro_series":
                result = get_macro_series(
                    client=client,
                    series_ids=list(args.get("series_ids", [])),
                    lookback=int(args.get("lookback", 6)),
                )
            else:
                return f"Error: unknown tool {name!r}"
            return json.dumps(result, default=str)
        except Exception as exc:  # noqa: BLE001 — tool errors are returned to the model, not raised
            logger.warning("data tool %s failed: %s", name, exc)
            return f"Error: {name} failed: {exc}"

    return execute_tool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dq/atlas/data/test_tools.py -m unit -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/olympus/atlas/data/tools.py tests/dq/atlas/data/test_tools.py
git commit -m "feat(atlas): in-process data ToolDefinitions + dispatcher"
```

---

### Task 3: `search_parameters` → `extra_body` in the LLM client (xAI-only)

**Files:**
- Modify: `digigraph/src/digigraph/llm.py` (`chat_completion` ~line 513; `chat_completion_with_tools` ~line 720)
- Test: `tests/dg/test_llm_search_params.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/dg/test_llm_search_params.py
from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from digigraph import llm


def _resp(text="ok"):
    m = MagicMock()
    m.choices = [MagicMock()]
    m.choices[0].message.content = text
    m.choices[0].message.tool_calls = None
    return m


@pytest.mark.unit
def test_search_params_forwarded_via_extra_body_for_xai(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "x")
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _resp()

    with patch.object(llm, "get_client_for_model") as gcm:
        gcm.return_value.chat.completions.create.side_effect = fake_create
        llm.chat_completion(
            "xai/grok-4.3",
            [{"role": "user", "content": "hi"}],
            search_parameters={"mode": "on", "sources": [{"type": "web"}]},
        )
    assert captured["extra_body"] == {"search_parameters": {"mode": "on", "sources": [{"type": "web"}]}}


@pytest.mark.unit
def test_search_params_ignored_for_non_xai(monkeypatch):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _resp()

    with patch.object(llm, "get_client_for_model") as gcm:
        gcm.return_value.chat.completions.create.side_effect = fake_create
        llm.chat_completion(
            "ollama/qwen3:8b",
            [{"role": "user", "content": "hi"}],
            search_parameters={"mode": "on"},
        )
    assert "extra_body" not in captured
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dg/test_llm_search_params.py -m unit -v`
Expected: FAIL — `chat_completion() got an unexpected keyword argument 'search_parameters'`

- [ ] **Step 3: Add `search_parameters` to `chat_completion`**

In `digigraph/src/digigraph/llm.py`, extend the `chat_completion` signature and kwargs assembly. Add the parameter after `max_tokens`:

```python
def chat_completion(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    tools: list[ToolDefinition] | None = None,
    tool_choice: str | ToolArguments = "auto",
    response_format: JsonSchemaResponseFormat | None = None,
    max_tokens: int | None = None,
    search_parameters: dict[str, Any] | None = None,
) -> str | tuple[str, list[ToolCallDict] | None]:
```

Then, where `kwargs` is built (just before `r = _create_with_retry(client, **kwargs)`), append:

```python
    if search_parameters is not None and provider == "xai":
        # xAI Live Search rides through the OpenAI-compatible client via extra_body.
        kwargs["extra_body"] = {"search_parameters": search_parameters}
    elif search_parameters is not None:
        logger.debug("search_parameters ignored for non-xAI model %s", effective_model)
```

(Note: `provider` is already bound at the top of `chat_completion` from `_parse_provider_prefix(model)`.)

- [ ] **Step 4: Pass `search_parameters` through `chat_completion_with_tools`**

Add `search_parameters: dict[str, Any] | None = None` to `chat_completion_with_tools`'s keyword args, and forward it in the non-streaming `do_one_turn` branch:

```python
        out = chat_completion(
            model, current, temperature=temperature, tools=tools, tool_choice="auto",
            search_parameters=search_parameters,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/dg/test_llm_search_params.py -m unit -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the existing llm suite (no regressions)**

Run: `pytest tests/dg/test_llm.py -m unit -q`
Expected: PASS (39 passed).

- [ ] **Step 7: Commit**

```bash
git add digigraph/src/digigraph/llm.py tests/dg/test_llm_search_params.py
git commit -m "feat(llm): forward xAI search_parameters via extra_body"
```

---

### Task 4: Live-search parameter builder + domain allowlist

**Files:**
- Create: `digiquant/src/digiquant/olympus/atlas/config/search_domains.yaml`
- Create: `digiquant/src/digiquant/olympus/atlas/data/live_search.py`
- Test: `tests/dq/atlas/data/test_live_search.py`

- [ ] **Step 1: Create the domain allowlist**

```yaml
# digiquant/src/digiquant/olympus/atlas/config/search_domains.yaml
# Curated allowlist for Grok Live Search web source — keeps day-to-day search
# flow consistent and high-signal. Edit to tune sources per signal.
web_allowed_websites:
  - reuters.com
  - apnews.com
  - bloomberg.com
  - cnbc.com
  - wsj.com
  - ft.com
  - sec.gov
  - federalreserve.gov
  - treasury.gov
  - cftc.gov
  - bls.gov
  - finance.yahoo.com
  - capitoltrades.com
# News + X sources are enabled without a domain restriction.
recency_days: 7
max_search_results: 8
```

- [ ] **Step 2: Write the failing test**

```python
# tests/dq/atlas/data/test_live_search.py
from __future__ import annotations
from datetime import date
import pytest
from digiquant.olympus.atlas.data.live_search import build_search_parameters


@pytest.mark.unit
def test_build_search_parameters_shape():
    sp = build_search_parameters(run_date=date(2026, 6, 8))
    assert sp["mode"] == "on"
    assert sp["return_citations"] is True
    assert sp["from_date"] == "2026-06-01"  # run_date - recency_days
    types = {s["type"] for s in sp["sources"]}
    assert {"web", "news", "x"} <= types
    web = next(s for s in sp["sources"] if s["type"] == "web")
    assert "reuters.com" in web["allowed_websites"]
    assert sp["max_search_results"] == 8
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/dq/atlas/data/test_live_search.py -m unit -v`
Expected: FAIL — `ModuleNotFoundError: ...data.live_search`

- [ ] **Step 4: Write the implementation**

```python
# digiquant/src/digiquant/olympus/atlas/data/live_search.py
"""Build xAI Live Search ``search_parameters`` from the curated domain allowlist."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "search_domains.yaml"


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    with open(_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_search_parameters(*, run_date: date) -> dict[str, Any]:
    """Return an xAI Live Search descriptor: web (allowlisted) + news + x, recent + cited."""
    cfg = _load_config()
    allowed = list(cfg.get("web_allowed_websites", []))
    recency = int(cfg.get("recency_days", 7))
    from_date = (run_date - timedelta(days=recency)).isoformat()
    sources: list[dict[str, Any]] = [{"type": "web"}, {"type": "news"}, {"type": "x"}]
    if allowed:
        # xAI caps allowed_websites at 5 per source; take the highest-priority slice.
        sources[0]["allowed_websites"] = allowed[:5]
    return {
        "mode": "on",
        "sources": sources,
        "from_date": from_date,
        "return_citations": True,
        "max_search_results": int(cfg.get("max_search_results", 8)),
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/dq/atlas/data/test_live_search.py -m unit -v`
Expected: PASS — but note the **5-domain cap** assertion: change the test to assert `"reuters.com" in web["allowed_websites"]` and `len(web["allowed_websites"]) == 5`. Update the test accordingly, re-run, expect PASS.

- [ ] **Step 6: Commit**

```bash
git add digiquant/src/digiquant/olympus/atlas/config/search_domains.yaml \
        digiquant/src/digiquant/olympus/atlas/data/live_search.py \
        tests/dq/atlas/data/test_live_search.py
git commit -m "feat(atlas): Grok Live Search parameter builder + domain allowlist"
```

---

### Task 5: `run_research_agent` tool-loop + validate-retry

**Files:**
- Modify: `digigraph/src/digigraph/graph/research_agent.py`
- Test: `tests/dg/test_research_agent_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/dg/test_research_agent_tools.py
from __future__ import annotations
import json
from unittest.mock import patch
import pytest
from pydantic import BaseModel
from digigraph.graph import research_agent


class _Out(BaseModel):
    regime: str
    note: str


@pytest.mark.unit
def test_tool_path_uses_chat_completion_with_tools_and_validates():
    calls = {}

    def fake_cwt(model, messages, tools, execute_tool, *, temperature=0.2,
                 max_tool_rounds=5, on_tool_step=None, search_parameters=None):
        calls["tools"] = tools
        calls["search_parameters"] = search_parameters
        # Simulate the model grounding then emitting valid JSON.
        execute_tool("get_macro_series", {"series_ids": ["DFF"]})
        return json.dumps({"regime": "risk_on", "note": "grounded"})

    executed = []
    with patch.object(research_agent, "chat_completion_with_tools", side_effect=fake_cwt):
        result = research_agent.run_research_agent(
            skill_text="s", phase_inputs={}, shared_context={},
            output_model=_Out, model="xai/grok-4.3",
            tools=[{"type": "function", "function": {"name": "get_macro_series"}}],
            execute_tool=lambda n, a: executed.append(n) or "{}",
            search_parameters={"mode": "on"},
        )
    assert result.regime == "risk_on"
    assert calls["search_parameters"] == {"mode": "on"}
    assert calls["tools"][0]["function"]["name"] == "get_macro_series"


@pytest.mark.unit
def test_no_tools_keeps_structured_call():
    with patch.object(research_agent, "chat_completion",
                      return_value='{"regime":"neutral","note":"x"}') as cc:
        result = research_agent.run_research_agent(
            skill_text="s", phase_inputs={}, shared_context={},
            output_model=_Out, model="xai/grok-4.3",
        )
    assert result.regime == "neutral"
    assert cc.called  # falls back to the structured-output path when no tools
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dg/test_research_agent_tools.py -m unit -v`
Expected: FAIL — `run_research_agent() got an unexpected keyword argument 'tools'`

- [ ] **Step 3: Add the import + new params**

In `digigraph/src/digigraph/graph/research_agent.py`, add to the imports:

```python
from digigraph.llm import (
    chat_completion,
    chat_completion_with_tools,
    get_model_for_mode,
    get_model_for_phase,
)
```

Extend `run_research_agent`'s signature with three keyword params (after `max_tokens`):

```python
    tools: list[dict[str, Any]] | None = None,
    execute_tool: Callable[[str, dict[str, Any]], str] | None = None,
    search_parameters: dict[str, Any] | None = None,
```

Add `from typing import Callable` to the typing import line.

- [ ] **Step 4: Branch the LLM call inside the retry loop**

Replace the body of the `for attempt in range(...)` loop's first statement (the `raw = chat_completion(...)` call) with a branch. Keep the existing `_strip_json_fence` + `model_validate` + retry-with-error-feedback logic unchanged:

```python
            if tools and execute_tool is not None:
                raw = chat_completion_with_tools(
                    effective_model,
                    messages,
                    tools=tools,
                    execute_tool=execute_tool,
                    temperature=temperature,
                    search_parameters=search_parameters,
                )
            else:
                raw = chat_completion(
                    effective_model,
                    messages,
                    temperature=temperature,
                    response_format=response_format,
                    max_tokens=max_tokens,
                    search_parameters=search_parameters,
                )
            if isinstance(raw, tuple):  # defensive: tuple only with tools
                raw = raw[0]
```

(The retry branch already appends an assistant+user correction message and re-loops; with tools that simply re-runs the tool loop asking for valid JSON. No other change needed.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/dg/test_research_agent_tools.py -m unit -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the dq atlas suite (no regressions in phases that still call without tools)**

Run: `pytest tests/dq/atlas -m unit -q -p no:cacheprovider --timeout=45`
Expected: PASS (same count as before this plan; the no-tools path is unchanged).

- [ ] **Step 7: Commit**

```bash
git add digigraph/src/digigraph/graph/research_agent.py tests/dg/test_research_agent_tools.py
git commit -m "feat(research-agent): tool-loop grounding + validate-retry (tools/search_parameters)"
```

---

### Task 6: Wire tools + search into the segment node factory

**Files:**
- Modify: `digiquant/src/digiquant/olympus/atlas/phases/_node_factory.py`
- Test: `tests/dq/atlas/test_node_factory_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/atlas/test_node_factory_tools.py
from __future__ import annotations
import dataclasses
from datetime import date
from unittest.mock import patch
import pytest

from digiquant.olympus.atlas.phases import _node_factory
from digiquant.olympus.atlas.phases.phase3_macro import build_phase3
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState


def _state():
    return AtlasResearchState(
        run_type="baseline", run_date=date(2026, 6, 8),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
    )


def _run_macro_node_capturing(monkeypatch, *, enabled: bool):
    """Build the real macro node, force its spec flags on, and capture the kwargs
    passed to run_research_agent."""
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1" if enabled else "0")
    captured: dict = {}

    # Avoid a real Supabase connection in the unit test.
    monkeypatch.setattr(_node_factory, "_atlas_data_client", lambda: object())

    # The macro PipelinePhase wraps one NodeSpec; grab its run() callable.
    node = build_phase3().nodes[0].run

    # Force the flags on the spec the node closes over. SegmentNodeSpec is a frozen
    # dataclass; if it is Pydantic in your tree, use `.model_copy(update=...)` instead.
    # (build_phase3 builds the node from module-level `_SPEC`; patch that symbol.)
    import digiquant.olympus.atlas.phases.phase3_macro as p3
    forced = dataclasses.replace(p3._SPEC, use_data_tools=True, live_search=True)
    monkeypatch.setattr(p3, "_SPEC", forced)
    node = build_phase3().nodes[0].run  # rebuild with forced spec

    def fake_rra(**kwargs):
        captured.update(kwargs)
        return forced.output_model.model_construct()

    with patch("digigraph.graph.research_agent.run_research_agent", side_effect=fake_rra):
        node(_state())
    return captured


@pytest.mark.unit
def test_node_passes_tools_and_search_when_enabled(monkeypatch):
    cap = _run_macro_node_capturing(monkeypatch, enabled=True)
    assert cap["tools"] is not None
    assert cap["execute_tool"] is not None
    assert cap["search_parameters"] is not None


@pytest.mark.unit
def test_node_passes_nothing_when_disabled(monkeypatch):
    cap = _run_macro_node_capturing(monkeypatch, enabled=False)
    assert cap["tools"] is None
    assert cap["search_parameters"] is None
```

> Executor note (two interface confirmations): (1) `build_phase3()` / the macro node
> wrapper — confirm the `PipelinePhase.nodes[0].run` accessor matches the real
> `build_segment_node` wiring (see `phase3_macro.build_phase3`). (2) `SegmentNodeSpec`
> copy: `dataclasses.replace` if it is a (frozen) dataclass — switch to
> `.model_copy(update=...)` if it is a Pydantic model. Both are one-line swaps.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/atlas/test_node_factory_tools.py -m unit -v`
Expected: FAIL (node does not yet build/pass tools).

- [ ] **Step 3: Add tool wiring to `build_segment_node`**

In `_node_factory.py`, import the data tool + live-search builders and a client accessor, and extend `SegmentNodeSpec` with two flags (default False): `use_data_tools: bool` and `live_search: bool`. In `_node`, after `inputs = inputs_builder(state, spec)` and before `run_research_agent(...)`:

```python
        tools = None
        execute_tool = None
        search_parameters = None
        if spec.use_data_tools and _data_tools_enabled():
            from digiquant.olympus.atlas.data.tools import DATA_TOOLS, build_data_tool_dispatcher
            tools = DATA_TOOLS
            execute_tool = build_data_tool_dispatcher(_atlas_data_client())
        if spec.live_search and _data_tools_enabled():
            from digiquant.olympus.atlas.data.live_search import build_search_parameters
            search_parameters = build_search_parameters(run_date=state.run_date)
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=inputs,
            shared_context=shared,
            output_model=spec.output_model,
            model=model,
            phase_slug=spec.segment_slug,
            tools=tools,
            execute_tool=execute_tool,
            search_parameters=search_parameters,
        )
```

Add the env gate + a memoized client helper at module scope (segment nodes don't
carry a Supabase client, so build one the same way the MCP tools and `preflight.py`
do — via `SupabaseConfig.from_env()` — and cache it so it isn't rebuilt per node):

```python
import os
from functools import lru_cache


def _data_tools_enabled() -> bool:
    return os.environ.get("ATLAS_DATA_TOOLS", "1").strip().lower() not in ("0", "false", "")


@lru_cache(maxsize=1)
def _atlas_data_client():
    from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client
    return build_client(SupabaseConfig.from_env())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/dq/atlas/test_node_factory_tools.py -m unit -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/olympus/atlas/phases/_node_factory.py \
        tests/dq/atlas/test_node_factory_tools.py
git commit -m "feat(atlas): wire data tools + live search into segment nodes (flagged)"
```

---

### Task 7: Set per-phase flags + tool-usage prompts

**Files:**
- Modify: phase spec modules under `digiquant/src/digiquant/olympus/atlas/phases/` (`phase3_macro.py`, `phase4_assetclass.py`, `phase5_equities.py`, the phase-1/2 alt/inst specs, phase-7C analyst spec)
- Modify: `digigraph/src/digigraph/graph/research_agent.py` (`ANALYST_SYSTEM`)
- Modify: relevant `skills/*/SKILL.md` under the atlas package
- Test: `tests/dq/atlas/test_phase_tool_flags.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/atlas/test_phase_tool_flags.py
import pytest
from digiquant.olympus.atlas.phases.phase3_macro import _SPEC as MACRO
from digiquant.olympus.atlas.phases.phase5_equities import _equity_spec  # adjust to actual symbol


@pytest.mark.unit
def test_macro_uses_data_tools_and_search():
    assert MACRO.use_data_tools is True
    assert MACRO.live_search is True  # intl-M2 fallback
```

> Executor note: align symbol names with each spec module (some expose `_SPEC`,
> others build specs in a factory). Set flags per the spec doc:
> - `use_data_tools=True`: macro, equity, sector-*, asset-classes, analysts.
> - `live_search=True`: macro (intl-M2 fallback), all alt-* and inst-* phases.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/atlas/test_phase_tool_flags.py -m unit -v`
Expected: FAIL — flags default False.

- [ ] **Step 3: Set the flags in each spec**

For each `SegmentNodeSpec(...)` construction, add `use_data_tools=` / `live_search=` per the table in the executor note above. Example (`phase3_macro.py`):

```python
_SPEC = SegmentNodeSpec(
    segment_slug="macro",
    # ...existing fields...
    use_data_tools=True,
    live_search=True,
)
```

- [ ] **Step 4: Update `ANALYST_SYSTEM`**

In `research_agent.py`, append to `ANALYST_SYSTEM`:

```python
ANALYST_SYSTEM = ANALYST_SYSTEM + """

Grounding with tools (when available):
- Use `get_price_technicals` / `get_macro_series` to fetch real prices, technicals, and
  macro values for this scope. Do not assert a number you did not retrieve.
- When web search is available, use it for news, sentiment, positioning, flows, and
  recent events; cite each source URL in the output's `sources` field.
- If a tool returns an error or no data, say so in the relevant field and lower conviction;
  never invent values.
"""
```

- [ ] **Step 5: Update the soft-phase SKILL.md files**

For each alt-/inst-/macro skill, add a "Data sources" line naming what to fetch (e.g. macro: "Call `get_macro_series` for M2SL, DFF, DGS10, T10Y2Y, VIXCLS, DTWEXBGS, T10YIE; web-search for any non-US M2 that is stale."). Keep edits to the body (below YAML frontmatter).

- [ ] **Step 6: Run tests + doc-links**

Run: `pytest tests/dq/atlas/test_phase_tool_flags.py -m unit -v` → PASS
Run: `python3 scripts/check_doc_links.py` → OK

- [ ] **Step 7: Commit**

```bash
git add digiquant/src/digiquant/olympus/atlas/phases/*.py \
        digigraph/src/digigraph/graph/research_agent.py \
        digiquant/src/digiquant/olympus/atlas/skills
git commit -m "feat(atlas): enable data-tool/live-search per phase + grounding prompts"
```

---

### Task 8: Expose the data queries as MCP tools

**Files:**
- Modify: `digiquant/src/digiquant/mcp_server.py`
- Test: `tests/dq/test_mcp_data_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/test_mcp_data_tools.py
import pytest
mcp_mod = pytest.importorskip("mcp.server.fastmcp")
from digiquant.mcp_server import create_mcp_server


@pytest.mark.unit
def test_data_tools_registered():
    server = create_mcp_server()
    # FastMCP exposes registered tools; assert our two are present.
    names = {t.name for t in server._tool_manager.list_tools()}  # FastMCP internal accessor
    assert "digiquant_get_price_technicals" in names
    assert "digiquant_get_macro_series" in names
```

> Executor note: if the FastMCP version's accessor differs, use the public
> `await server.list_tools()` in an async test, or assert via the decorator
> registry the installed version exposes. Keep the assertion to "both tool names
> are registered."

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/test_mcp_data_tools.py -m unit -v`
Expected: FAIL (tools not registered) or SKIP if `mcp` not installed — install with `pip install -e "./digiquant[mcp]"` first.

- [ ] **Step 3: Register the tools**

In `create_mcp_server()` (after the existing `@mcp.tool()` defs), add:

```python
    @mcp.tool()
    def digiquant_get_price_technicals(ticker: str, lookback: int = 20) -> str:
        """Latest technical indicators + recent window for a ticker (JSON)."""
        import json
        from digiquant.olympus.atlas.data.queries import get_price_technicals
        from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client
        client = build_client(SupabaseConfig.from_env())
        return json.dumps(get_price_technicals(client=client, ticker=ticker, lookback=lookback), default=str)

    @mcp.tool()
    def digiquant_get_macro_series(series_ids: list[str], lookback: int = 6) -> str:
        """Latest values + recent window for FRED macro series ids (JSON)."""
        import json
        from digiquant.olympus.atlas.data.queries import get_macro_series
        from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client
        client = build_client(SupabaseConfig.from_env())
        return json.dumps(get_macro_series(client=client, series_ids=series_ids, lookback=lookback), default=str)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dq/test_mcp_data_tools.py -m unit -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/mcp_server.py tests/dq/test_mcp_data_tools.py
git commit -m "feat(mcp): expose price-technicals + macro-series data tools"
```

---

### Task 9: Full gate + ARCHITECTURE docs

**Files:**
- Modify: `digiquant/src/digiquant/olympus/atlas/ARCHITECTURE.md` (data-flow section)
- Modify: `docs/atlas/token-budget.md` (note tool-grounding)

- [ ] **Step 1: Update ARCHITECTURE.md**

Document the new data flow: preflight freshness probe (unchanged) → phases run a tool loop (`get_price_technicals`/`get_macro_series` + Grok Live Search) → validate-retry → publish. Note the `ATLAS_DATA_TOOLS` env gate and the `search_domains.yaml` allowlist.

- [ ] **Step 2: Run the scoring gate on the full diff**

Run: `python3 scripts/score.py --staged` (after `git add -A`)
Expected: all four dimensions ≥ threshold. Fix any flagged item.

- [ ] **Step 3: Run ruff + targeted tests**

Run: `ruff check digiquant digigraph && ruff format --check digiquant/src/digiquant/olympus/atlas/data`
Run: `pytest tests/dq/atlas tests/dg/test_llm.py tests/dg/test_llm_search_params.py tests/dg/test_research_agent_tools.py -m unit -q -p no:cacheprovider --timeout=60`
Expected: all green.

- [ ] **Step 4: Commit + open PR**

```bash
git add -A
git commit -m "docs(atlas): data-wiring architecture + token-budget notes (#566)"
git push -u origin task/566-atlas-data-wiring
gh pr create --base develop --title "feat(atlas): wire real data into research phases — data tool + Grok Live Search (#566)" --body "Implements docs/superpowers/specs/2026-06-08-atlas-data-wiring-design.md. Refs #566, #565."
```

---

### Task 10: Live validation on Grok (post-merge gate)

**Files:** none (operational)

- [ ] **Step 1: Verify Live Search rides `extra_body` against the real API**

Before relying on Component B, run `validate-providers.py`-style smoke or a one-off `chat_completion("xai/grok-4.3", [...], search_parameters=build_search_parameters(run_date=today))` with `XAI_API_KEY` set; confirm the response includes citations. If xAI rejects `search_parameters` via `extra_body`, fall back to a search-only pass then a tool pass (documented risk in the spec).

- [ ] **Step 2: Trigger an Atlas baseline on Grok**

Run: `gh workflow run atlas-baseline.yml --ref develop` (after merge). Watch with `gh run watch <id>`.

- [ ] **Step 3: Confirm substantive output**

Query the digest for the run date and assert `regime`/segments contain real reads (not "Insufficient Data") and `sources` are populated. If soft phases are still thin, capture which signals need dedicated ingestion and file under #565.
