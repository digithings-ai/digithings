# digigraph Gloomberb Attribution Preservation in Clipped Tool Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When digigraph's generic tool-result trace clipper cuts a large `digifetch_*` envelope, the emitted trace result still carries the §7 attribution block (`attribution`, `delay_notice`, `source_url`) so the digichat attribution line (#4130) renders instead of vanishing.

**Architecture:** A new bounded extractor in `digigraph/src/digigraph/workflow.py` hoists the §7 keys from the **raw** result — structured envelope dicts or the serialized envelope inside the MCP client's opaque `{"ok": true, "text": "<json>"}` wrapper — and a new render helper attaches them as top-level keys on the emitted `result` object, ahead of the existing clip. The truncation preview budget shrinks by the hoisted block's serialized size and is enforced on the re-serialized record (escaped quotes in the preview re-expand on serialization), so the 12,000-char record cap is unchanged. No frontend code changes: the digichat adapter already passes `payload.result` through and the #4130 renderer already reads top-level keys off it. Tasks 3–4 add frontend contract-pin tests only.

**Tech Stack:** Python 3.12 + pytest (`unit` marker, root `pytest.ini`), digigraph trace pipeline (`workflow.py`, `TraceEventV1`), ruff (line length 100); TypeScript + Vitest 4 in `apps/digichat` and `packages/ui` (`@digithings/ui`).

**Spec:** `docs/superpowers/specs/2026-09-16-digigraph-gloomberb-attribution-clipping-design.md` (§3 result-level hoist, §4 contracts, §5 normative values)

**Issue:** [#4131](https://github.com/digithings-ai/digithings/issues/4131) — `component:digigraph`, base `module/digigraph` per `scripts/project_routing.json`; the frontend pins route `component:website` → `develop` and `component:digichat` → `module/digichat`.

## Global Constraints

- **Worktree/branch:** start with `make task ISSUE=4131` (it fetches `origin` and cuts `task/4131-…` from `origin/module/digigraph`; it refuses a stale module branch — sync `module/digigraph` first if it does). Tasks 1–2 run on that branch. Tasks 3 and 4 are **test-only** branches cut separately: `chore/gloomberb-attribution-render-pin` from `origin/develop` and `chore/gloomberb-adapter-attribution-pin` from `origin/module/digichat`. Never mix them into the digigraph branch.
- **No new dependencies** of any kind (no Python, no npm). Nothing in this plan adds a package.
- **Result size caps stay unchanged.** `_MAX_TOOL_RESULT_CHARS = 12_000` (`digigraph/src/digigraph/workflow.py:115`), the 2,000-char scalar cap (`workflow.py:121`), and digichat's `12_000` / `32` / `50` / `300` caps (`apps/digichat/src/lib/chat-activity.ts:30,39-42`) all stay exactly as they are. The fix only reorders/preserves keys; the truncated preview budget shrinks when the hoisted block is present.
- **Polars only** for data paths (this change touches no data path — no pandas anywhere); **Pydantic v2 strict** models only (no new models); **ruff** line length 100, `ruff check digigraph/ && ruff format --check digigraph/` clean.
- **Lowercase digi\* naming** in prose, docs, commit messages, and PR text (`digigraph`, `digichat`, `digiquant`). "Gloomberb" is an upstream product name and keeps its casing.
- **Every change traces to #4131:** the `task/4131-…` branch (Tasks 1–2), `Fixes #4131` in the digigraph PR, `Refs #4131` in the two pin PRs.
- **No human gate:** no new dependencies, no new network calls, no auth/JWT/crypto, no broker or live-trading paths. State this in each PR body.
- Do **not** modify the digiquant envelope serializer, the digichat sanitizer, the digiweb renderer, or the model-facing tool message. Tasks 3–4 touch test files only.
- Do not push anything before Task 5.

**Files touched overall:**
- Modify: `digigraph/src/digigraph/workflow.py:165-167` (insert helpers), `:703-718` (rewire the generic branch)
- Modify: `digigraph/ARCHITECTURE.md:118-132` (trace-contract note)
- Create: `tests/dg/test_tool_result_attribution.py`
- Modify: `packages/ui/src/components/chat/digichat-thread.render.test.tsx` (fixture + one test)
- Modify: `apps/digichat/src/lib/adapters/digithings/activity/tool-result.test.ts` (one test)

---

### Task 1: digigraph — hoist §7 attribution out of the clip (RED → GREEN)

**Files:**
- Modify: `digigraph/src/digigraph/workflow.py:165-167` (insert constants/helpers between `_clip_tool_result` — which ends at `:164` — and `_audit_digi_kwargs` at `:167`)
- Modify: `digigraph/src/digigraph/workflow.py:703-718` (rewire the generic `tool_result` branch)
- Modify: `digigraph/ARCHITECTURE.md:118-132` (trace-contract sentence)
- Test: `tests/dg/test_tool_result_attribution.py` (create)

**Interfaces:**
- Consumes: `_clip_tool_result(result: Any, _depth: int = 0) -> Any | None` and `_MAX_TOOL_RESULT_CHARS` (`workflow.py:115-164`); the generic `tool_result` event dict built by digillm (`digillm/src/digillm/client.py:2168-2172`) and the MCP text wrapper `{"ok": True, "text": "<joined text>"}` from `digigraph/src/digigraph/orchestration/mcp_client.py:643-669`; the §7 key names from `digiquant/src/digiquant/data/gloomberb/attribution.py:34-38`.
- Produces: `_ATTRIBUTION_KEYS: tuple[str, str, str]`; `_extract_attribution(value: Any, _depth: int = 0) -> dict[str, str]`; `_render_clipped_tool_result(result_data: dict[str, Any]) -> Any | None` (returns `None` exactly when today's clip returns `None`). The emitted trace result gains the §7 keys as leading top-level string keys when present — Tasks 2–4 pin this shape.

- [ ] **Step 1: Write the failing end-to-end trace test**

Create `tests/dg/test_tool_result_attribution.py`:

```python
"""§7 attribution preservation when generic tool results are clipped (#4131)."""

from __future__ import annotations

import json
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest
from digigraph.models import WorkflowRequest
from digigraph.workflow import _MAX_TOOL_RESULT_CHARS, run_digigraph_workflow_streaming

# Mirrors digiquant/src/digiquant/data/gloomberb/attribution.py:21-23. digigraph
# never imports digiquant packages, so the strings are inlined (the digiweb
# parity test reads the Python file instead — gloomberb.test.ts:120-141).
_ATTRIBUTION = "Sourced from Gloomberb"
_DELAY_NOTICE = "Data delayed up to 15 minutes"
_SOURCE_URL = "https://term.gloom.sh/?ticker=AAPL"


def _envelope_text(rows: int = 120) -> str:
    """A digifetch_price_history envelope as ``gloomberb_envelope_json`` emits it.

    The §7 block is appended LAST (agent_tools.py:161-166) — the ordering that
    loses it to the 2,000-char scalar cap once the MCP client wraps the string
    in ``{"ok": true, "text": ...}`` (mcp_client.py:657-669).
    """
    payload: dict = {
        "data": {
            "bars": [
                {"date": f"2025-01-{(i % 28) + 1:02d}", "close": 100.0 + i}
                for i in range(rows)
            ]
        },
        "stale": False,
    }
    payload["attribution"] = _ATTRIBUTION
    payload["delay_notice"] = _DELAY_NOTICE
    payload["source_url"] = _SOURCE_URL
    return json.dumps(payload, indent=2, default=str)


def _tool_result_traces(queue: Queue) -> list[dict]:
    events = []
    while not queue.empty():
        events.append(queue.get())
    return [e[1] for e in events if e[0] == "trace" and e[1].get("type") == "tool_result"]


@pytest.mark.unit
def test_clipped_digifetch_envelope_keeps_attribution_in_the_trace() -> None:
    queue: Queue = Queue()
    tool_payload = {
        "name": "digiquant_digifetch_price_history",
        "ok": True,
        "text": _envelope_text(),
    }

    def fake_stream(
        initial, config=None, stream_mode=None, version=None, durability=None, subgraphs=None
    ):
        # digillm's run_tools fires this shape via on_tool_step; the research
        # node forwards it as a stream_mode=["updates", "custom"] custom part.
        yield {"type": "custom", "ns": (), "data": ("tool_result", tool_payload)}

    mock_graph = MagicMock()
    mock_graph.stream.side_effect = fake_stream
    mock_graph.get_state.return_value = MagicMock(values={})

    with patch("digigraph.workflow.build_workflow_graph", return_value=mock_graph):
        run_digigraph_workflow_streaming(WorkflowRequest(prompt="AAPL history"), queue)

    traces = _tool_result_traces(queue)
    assert len(traces) == 1
    result = traces[0]["payload"]["result"]
    assert result["attribution"] == _ATTRIBUTION
    assert result["delay_notice"] == _DELAY_NOTICE
    assert result["source_url"] == _SOURCE_URL
    # Caps unchanged: the string scalar is still cut at 2,000 chars and the
    # whole emitted record stays within the 12,000-char trace cap.
    assert len(result["text"]) == 2000
    assert len(json.dumps(result)) <= _MAX_TOOL_RESULT_CHARS
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/dg/test_tool_result_attribution.py -v`
Expected: FAIL — `1 failed`, `KeyError: 'attribution'` (pre-fix the trace result is `{"ok": True, "text": "<first 2000 chars>"}`; the §7 block is appended after the cut).

- [ ] **Step 3: Add the extractor and renderer**

In `digigraph/src/digigraph/workflow.py`, insert between `_clip_tool_result`'s closing line (`:164`) and `_audit_digi_kwargs` (`:167`):

```python
# §7 attribution keys appended to digifetch_* payloads
# (digiquant/src/digiquant/data/gloomberb/agent_tools.py::gloomberb_envelope_json).
# Hoisted out of the size-capped result so the digichat attribution line (#4130)
# still renders when the payload is clipped (#4131).
_ATTRIBUTION_KEYS = ("attribution", "delay_notice", "source_url")
_MAX_ATTRIBUTION_WALK_DEPTH = 3
_MAX_ATTRIBUTION_WALK_ITEMS = 64


def _attribution_from_mapping(value: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in _ATTRIBUTION_KEYS:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            out[key] = item
    return out


def _extract_attribution(value: Any, _depth: int = 0) -> dict[str, str]:
    """Find the §7 attribution block on a raw tool result (#4131).

    Handles a structured envelope and the MCP client's opaque wrapper
    (``orchestration/mcp_client.py``: ``{"ok": true, "text": "<json>"}``): the
    envelope appends the block LAST (``gloomberb_envelope_json``), so the
    wrapper's 2,000-char scalar cap cuts it before any reader sees a key.
    Bounded walk; malformed JSON is skipped, never raised.
    """
    if _depth > _MAX_ATTRIBUTION_WALK_DEPTH:
        return {}
    if isinstance(value, dict):
        found = _attribution_from_mapping(value)
        if found:
            return found
        items = list(value.values())
    elif isinstance(value, list):
        items = list(value)
    elif isinstance(value, str):
        if '"attribution"' not in value:
            return {}
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return _extract_attribution(parsed, _depth + 1)
    else:
        return {}
    for item in items[:_MAX_ATTRIBUTION_WALK_ITEMS]:
        found = _extract_attribution(item, _depth + 1)
        if found:
            return found
    return {}


def _render_clipped_tool_result(result_data: dict[str, Any]) -> Any | None:
    """Render a generic tool result for the trace, preserving §7 provenance.

    The §7 keys are hoisted from the raw result before the clip and attached
    ahead of it: the digichat attribution line (#4130) reads them off the
    emitted result (``packages/ui/src/lib/gloomberb.ts``), and the
    scalar cap leaves no key structure to read once a string is cut.
    """
    attribution = _extract_attribution(result_data)
    clipped_result = _clip_tool_result(result_data)
    if clipped_result is None:
        return None
    try:
        serialized = json.dumps(clipped_result)
        rendered: Any = clipped_result
        if len(serialized) > _MAX_TOOL_RESULT_CHARS:
            budget = _MAX_TOOL_RESULT_CHARS - 100
            if attribution:
                budget -= len(json.dumps(attribution))
            preview = serialized[:budget]
            # The slice is JSON text: its quote characters escape again when the
            # record is re-serialized, so measure the record, not the slice, and
            # shrink until it fits. The §7 keys are never trimmed.
            while True:
                rendered = {
                    **attribution,
                    "truncated": True,
                    "preview": preview + "… [truncated]",
                }
                if len(json.dumps(rendered)) <= _MAX_TOOL_RESULT_CHARS or not preview:
                    break
                preview = preview[:-64]
    except (TypeError, ValueError):
        rendered = {"preview": str(clipped_result)[:2000]}
    if attribution and isinstance(rendered, dict):
        rendered = {**attribution, **rendered}
    return rendered
```

- [ ] **Step 4: Rewire the generic `tool_result` branch**

In `workflow.py:703-718`, replace:

```python
                result_data = {k: v for k, v in data.items() if k != "name"}
                clipped_result = _clip_tool_result(result_data)
                if clipped_result is not None:
                    rendered = clipped_result
                    try:
                        if len(json.dumps(clipped_result)) > _MAX_TOOL_RESULT_CHARS:
                            rendered = {
                                "truncated": True,
                                "preview": json.dumps(clipped_result)[
                                    : _MAX_TOOL_RESULT_CHARS - 100
                                ]
                                + "… [truncated]",
                            }
                    except (TypeError, ValueError):
                        rendered = {"preview": str(clipped_result)[:2000]}
                    generic_payload["result"] = rendered
```

with:

```python
                result_data = {k: v for k, v in data.items() if k != "name"}
                rendered = _render_clipped_tool_result(result_data)
                if rendered is not None:
                    generic_payload["result"] = rendered
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/dg/test_tool_result_attribution.py -v`
Expected: PASS — `1 passed`.

- [ ] **Step 6: Run the digigraph suite and lint**

Run: `pytest -m unit tests/dg/ -q`
Expected: no new failures (pre-existing suite baseline unchanged).

Run: `ruff check digigraph/ && ruff format --check digigraph/`
Expected: clean (if `ruff format` wants the new code reformatted, run `ruff format digigraph/src/digigraph/workflow.py` and re-check).

- [ ] **Step 7: Document the trace-contract change**

In `digigraph/ARCHITECTURE.md:118-132`, extend the sentence containing
``(`_clip_tool_result`, 12_000-char JSON cap with truncated preview)`` with:

```
When the raw result carries the §7 attribution block
(`attribution` / `delay_notice` / `source_url`, appended last by
digiquant's `gloomberb_envelope_json`), those keys are hoisted out of the
clip and attached ahead of the emitted `result` — structured envelope or
the MCP `{"ok": true, "text": …}` wrapper alike — because a string scalar
is cut at 2,000 chars with no key structure left to read, and the digichat
attribution line (#4130) reads them off the result object (#4131). The
truncated preview budget shrinks by the hoisted block and is enforced on the
re-serialized record so the 12_000-char cap is unchanged.
```

- [ ] **Step 8: Commit**

```bash
git add digigraph/src/digigraph/workflow.py digigraph/ARCHITECTURE.md tests/dg/test_tool_result_attribution.py
git commit -m "fix(digigraph): preserve Gloomberb attribution when tool results are clipped (#4131)"
```

---

### Task 2: digigraph regression pins — scalar, structured, malformed shapes

**Files:**
- Modify: `tests/dg/test_tool_result_attribution.py` (extend the import; append 6 tests)

**Interfaces:**
- Consumes: `_render_clipped_tool_result` and `_extract_attribution` (Task 1); `_clip_tool_result` and `_MAX_TOOL_RESULT_CHARS` (existing, `workflow.py:115-164`); `_envelope_text` (Task 1).
- Produces: behavior pins for the shapes the fix must leave alone (huge non-JSON scalars, unattributed results) and for the shapes it must handle (small envelope, structured hub envelope, malformed JSON, wide structured truncation).

These tests are expected to **pass immediately** after Task 1 — they are regression pins, not RED steps. If any fails, Task 1's implementation is wrong.

- [ ] **Step 1: Extend the import block**

Replace the `from digigraph.workflow import …` line in `tests/dg/test_tool_result_attribution.py` with:

```python
from digigraph.workflow import (
    _MAX_TOOL_RESULT_CHARS,
    _clip_tool_result,
    _render_clipped_tool_result,
    run_digigraph_workflow_streaming,
)
```

- [ ] **Step 2: Append the regression tests**

Append to `tests/dg/test_tool_result_attribution.py`:

```python
@pytest.mark.unit
def test_small_envelope_keeps_attribution() -> None:
    rendered = _render_clipped_tool_result({"ok": True, "text": _envelope_text(rows=2)})
    assert rendered["attribution"] == _ATTRIBUTION
    assert rendered["delay_notice"] == _DELAY_NOTICE
    assert rendered["source_url"] == _SOURCE_URL
    assert rendered["ok"] is True


@pytest.mark.unit
def test_structured_hub_envelope_keeps_attribution() -> None:
    raw = {
        "ok": True,
        "service": "digiquant",
        "tool": "digifetch_quote",
        "data": {
            "data": {"quote": {"symbol": "AAPL", "price": 200.0}},
            "attribution": _ATTRIBUTION,
            "delay_notice": _DELAY_NOTICE,
            "source_url": _SOURCE_URL,
        },
    }
    rendered = _render_clipped_tool_result(raw)
    assert rendered["attribution"] == _ATTRIBUTION
    assert rendered["delay_notice"] == _DELAY_NOTICE
    assert rendered["source_url"] == _SOURCE_URL


@pytest.mark.unit
def test_large_non_json_scalar_is_capped_without_attribution() -> None:
    rendered = _render_clipped_tool_result({"ok": True, "text": "x" * 50_000})
    assert rendered == {"ok": True, "text": "x" * 2000}


@pytest.mark.unit
def test_malformed_json_string_does_not_raise() -> None:
    rendered = _render_clipped_tool_result({"ok": True, "text": '{"attribution": '})
    assert rendered == {"ok": True, "text": '{"attribution":'}


@pytest.mark.unit
def test_unattributed_result_is_unchanged() -> None:
    raw = {"connections": [{"name": "a", "id": "1"}]}
    assert _render_clipped_tool_result(raw) == _clip_tool_result(raw)


@pytest.mark.unit
def test_truncated_structured_record_stays_within_the_cap() -> None:
    raw = {
        "attribution": _ATTRIBUTION,
        "delay_notice": _DELAY_NOTICE,
        "source_url": _SOURCE_URL,
        "rows": ["row-" + "x" * 400 for _ in range(50)],
    }
    rendered = _render_clipped_tool_result(raw)
    assert rendered["truncated"] is True
    assert rendered["preview"].endswith("… [truncated]")
    assert rendered["attribution"] == _ATTRIBUTION
    # The preview slice is itself JSON text: its quote characters escape again
    # when the record is re-serialized, so the bound must hold on the
    # re-serialized record (12,023 chars pre-fix), not on the raw slice.
    assert len(json.dumps(rendered)) <= _MAX_TOOL_RESULT_CHARS
```

- [ ] **Step 3: Run the tests**

Run: `pytest tests/dg/test_tool_result_attribution.py -v`
Expected: PASS — `7 passed`.

- [ ] **Step 4: Run the suite and lint**

Run: `pytest -m unit tests/dg/ -q && ruff check digigraph/ && ruff format --check tests/dg/test_tool_result_attribution.py`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/dg/test_tool_result_attribution.py
git commit -m "test(digigraph): pin §7 attribution survival across clip shapes (#4131)"
```

---

### Task 3: digiweb renderer pin — attribution renders on a clipped result

**Files:**
- Modify: `packages/ui/src/components/chat/digichat-thread.render.test.tsx:77` (insert the fixture after `GLOOMBERB_MESSAGES`) and `:401` (insert the test after `credits Gloomberb in the expanded tool result pane`)

**Interfaces:**
- Consumes: the emitted result contract from Task 1/§4 (top-level `attribution` / `delay_notice` / `source_url` on the result object); the existing mount harness and `GLOOMBERB_MESSAGES` fixture conventions in this file (`:57-77`, `:380-401`).
- Produces: a pinned renderer contract — this test passes immediately (the helper already reads the shape); it exists so the digigraph fix cannot drift back to burying the block.

Branch: `chore/gloomberb-attribution-render-pin` cut from `origin/develop` (`component:website` is one-hop). Do not commit this file on the Task 1 branch.

- [ ] **Step 1: Insert the clipped-result fixture**

In `packages/ui/src/components/chat/digichat-thread.render.test.tsx`, after the `GLOOMBERB_MESSAGES` array (ends `:77`), add:

```tsx
const GLOOMBERB_CLIPPED_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "g3",
        toolName: "digiquant_digifetch_price_history",
        argsText: '{"symbol":"AAPL","resolution":"1d"}',
        // The shape digigraph emits post-#4131: §7 keys hoisted ahead of the
        // clipped scalar, so the attribution line renders without parsing text.
        result: {
          result: {
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
            source_url: "https://term.gloom.sh/?ticker=AAPL",
            ok: true,
            text: `${"x".repeat(2000)}… [truncated]`,
          },
        },
      },
      { type: "text", text: "history ready" },
    ],
  },
];
```

- [ ] **Step 2: Insert the render test**

After the `"credits Gloomberb in the expanded tool result pane"` test (ends `:401`), add:

```tsx
  it("credits Gloomberb when the tool result was clipped to its text preview", async () => {
    const { host, unmount } = await mount({
      initialMessages: GLOOMBERB_CLIPPED_MESSAGES,
      toolCallsMode: "expanded",
    });
    await act(async () => {});
    const trigger = host.querySelector('[data-slot="tool-fallback-trigger"]');
    expect(trigger).toBeTruthy();
    await act(async () => {
      trigger?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(host.textContent).toContain("Sourced from Gloomberb");
    expect(host.textContent).toContain("Data delayed up to 15 minutes");
    expect(
      host.querySelector('a[href="https://term.gloom.sh/?ticker=AAPL"]'),
    ).toBeTruthy();
    unmount();
  });
```

- [ ] **Step 3: Run the test**

Run: `npm --workspace @digithings/ui run test -- src/components/chat/digichat-thread.render.test.tsx`
Expected: PASS — the whole file green including the new case. This is a contract pin; a failure means the digigraph shape drifted from §4 or the renderer regressed.

- [ ] **Step 4: Commit**

```bash
git add packages/ui/src/components/chat/digichat-thread.render.test.tsx
git commit -m "test(digiweb): pin Gloomberb attribution rendering for clipped results (#4131)"
```

---

### Task 4: digichat adapter pin — §7 keys survive the span sanitizer

**Files:**
- Modify: `apps/digichat/src/lib/adapters/digithings/activity/tool-result.test.ts` (append one test inside the existing `describe("tool_result trace (generic MCP completion)")` block, after `:51`)

**Interfaces:**
- Consumes: `mapDigigraphTraceToSpans` from `./index` (existing import at `:2`), which runs `sanitizeActivitySpan` — the `chat-activity.ts` sanitizer with the 300-char record-value cap (`:30`, applied `:218-220`) and the 12k record cap (`:40`, applied `:230-234`).
- Produces: a pinned adapter contract — the §7 keys stay on `span.toolResult` even though the `text` scalar is cut; this passes immediately and guards the front-side caps the digigraph fix depends on.

Branch: `chore/gloomberb-adapter-attribution-pin` cut from `origin/module/digichat` (`component:digichat` is two-hop). Do not commit this file on the Task 1 branch.

- [ ] **Step 1: Append the adapter pin**

In `apps/digichat/src/lib/adapters/digithings/activity/tool-result.test.ts`, after the `"keeps args and marks failed status through"` test (ends `:51`), add:

```ts
  it("keeps the hoisted §7 attribution keys on a clipped digifetch result (#4131)", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "tool_result",
        payload: {
          tool: "digiquant_digifetch_price_history",
          status: "completed",
          result: {
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
            source_url: "https://term.gloom.sh/?ticker=AAPL",
            ok: true,
            text: `${"x".repeat(2000)}… [truncated]`,
          },
        },
      },
      "full",
    );
    expect(spans).toHaveLength(1);
    const result = spans[0]?.toolResult as Record<string, unknown>;
    // The §7 block is short and survives the sanitizer whole; the text scalar
    // is what the caps cut (and it is never parsed for attribution).
    expect(result.attribution).toBe("Sourced from Gloomberb");
    expect(result.delay_notice).toBe("Data delayed up to 15 minutes");
    expect(result.source_url).toBe("https://term.gloom.sh/?ticker=AAPL");
    expect(String(result.text).length).toBeLessThan(2000);
  });
```

- [ ] **Step 2: Run the test**

Run: `npm run test --workspace digichat -- src/lib/adapters/digithings/activity/tool-result.test.ts`
Expected: PASS — `4 passed` in the file. This is a contract pin; a failure means the digichat sanitizer no longer passes the §7 keys through (raise it on the issue rather than editing the sanitizer inside this fix).

- [ ] **Step 3: Commit**

```bash
git add apps/digichat/src/lib/adapters/digithings/activity/tool-result.test.ts
git commit -m "test(digichat): pin §7 attribution keys through the activity span sanitizer (#4131)"
```

---

### Task 5: Ship — digigraph PR first, then the two pin PRs

**Files:** none (git/GitHub only).

**Interfaces:**
- Consumes: the three task branches from Tasks 1–2, 3, and 4.
- Produces: the fix merged into `module/digigraph` (`Fixes #4131`) and the two test-only pins merged per routing.

- [ ] **Step 1: Push and open the digigraph PR**

Run (on the `task/4131-…` worktree):

```bash
git push -u origin HEAD
gh pr create --base module/digigraph \
  --title "fix(digigraph): preserve Gloomberb attribution when tool results are clipped (#4131)" \
  --body "$(cat <<'EOF'
Fixes #4131.

When digigraph clips a large tool result, the §7 Gloomberb attribution block
(attribution / delay_notice / source_url) is hoisted out of the clip and
attached ahead of the emitted trace result, so the digichat attribution line
from #4130 renders instead of vanishing. The block is extracted from the raw
result (structured envelope or the MCP `{"ok": true, "text": …}` wrapper)
before the 2,000-char scalar cap can cut it; the truncated preview budget
shrinks by the hoisted block so the 12,000-char cap is unchanged. Model-facing
tool text is untouched.

Spec: docs/superpowers/specs/2026-09-16-digigraph-gloomberb-attribution-clipping-design.md
Tests: pytest tests/dg/test_tool_result_attribution.py -v; pytest -m unit tests/dg/ -q;
ruff check digigraph/ && ruff format --check digigraph/.

No human gate: no new dependencies, no new network calls, no auth/crypto,
no broker/live-trading paths.
EOF
)"
```

- [ ] **Step 2: Review coverage, then merge into `module/digigraph`**

After CI is green and the branch is unconflicted: run the in-session fresh-context review (`/review <PR>`) per `docs/agents/CODE_REVIEW_POLICY.md`, fix findings on the branch, post the `<!-- in-session-review -->` findings comment, apply `reviewed:agent`, then `gh pr merge <N>`. Not on the human-gate list (`digigraph/` trace rendering only) — agent merge is allowed once merge-ready.

- [ ] **Step 3: Push and merge the two pin PRs**

```bash
git push -u origin chore/gloomberb-attribution-render-pin
gh pr create --base develop \
  --title "test(digiweb): pin Gloomberb attribution rendering for clipped results (#4131)" \
  --body "Refs #4131. Test-only pin for the shape digigraph now emits (spec §4). No human gate."
gh pr merge <N>

git push -u origin chore/gloomberb-adapter-attribution-pin
gh pr create --base module/digichat \
  --title "test(digichat): pin §7 attribution keys through the activity span sanitizer (#4131)" \
  --body "Refs #4131. Test-only pin guarding the chat-activity caps the digigraph fix depends on. No human gate."
gh pr merge <N>
```

Test-only additions: merge when CI is green; note the hatch used in the merge comment (`reviewed:owner`/in-session review per policy — a ritual is not required for a two-test diff).

---

## Self-Review

- **Spec coverage:** §3 chosen design (extractor + render helper + rewire) → Task 1. §4 result contract → Tasks 1–4 assertions. §5 normative values (key names, caps, budget, walk bounds, parse guard) → Task 1 code + Task 2 `test_truncated_structured_record_stays_within_the_cap`. §6 rollout (digigraph first, pins independent) → Tasks 3–5 bases/order. §7 verification → Task commands. §8 risks (front-side re-truncation, malformed JSON, scalar shape, unattributed parity) → Task 2 tests. §9 out of scope respected (no serializer, sanitizer, renderer, or cap edits). §10 Q2/Q3 → the pin assertions and the budget derivation.
- **Placeholder scan:** no TBD/TODO; every step carries its code, command, and expected output. The two frontend tasks are labeled **contract pins** (expected PASS) rather than RED steps, with the reason stated — the only RED/GREEN cycle is Task 1, where the bug lives.
- **Type consistency:** `_render_clipped_tool_result(result_data: dict[str, Any]) -> Any | None` is used identically in `workflow.py`, Task 1's test, and Task 2's tests; `_extract_attribution(value, _depth=0) -> dict[str, str]` matches its call sites; the three key names are spelled identically in the Python constant, both vitest pins, and the spec's §4 JSON examples; `_MAX_TOOL_RESULT_CHARS` is imported (not redefined) in tests.

**Execution handoff:** after approval, offer (1) subagent-driven (recommended) or (2) inline execution per the writing-plans skill.
