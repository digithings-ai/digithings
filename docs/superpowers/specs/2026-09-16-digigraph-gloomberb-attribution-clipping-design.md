# digigraph Gloomberb Attribution Preservation in Clipped Tool Results — Design Spec

> **For agentic workers:** This is a DESIGN SPEC, not an implementation plan.
> Do not implement from this file. The implementation plan (writing-plans skill)
> is written only after the user approves this spec.

**Date:** 2026-09-16 (evidence re-verified against the worktree at
`origin/develop` `118966117`)
**Status:** draft — awaiting approval
**Issue:** [#4131](https://github.com/digithings-ai/digithings/issues/4131) —
`fix(digigraph): preserve Gloomberb attribution when tool results are clipped`
(`component:digigraph`, `priority:low`). Follow-up of #4130 (phase 4 of #4110,
refs #4098).
**Human gate:** **not triggered.** No new dependencies, no new network calls,
no auth/JWT/crypto, no broker or live-trading path. The code change is a pure
in-process transformation of an existing trace payload.

---

## 1. Goal and scope

When a `digifetch_*` tool result is large enough for digigraph's generic
tool-result trace clipper to cut it, the emitted trace must still carry the §7
attribution block — `attribution`, `delay_notice`, `source_url` — so the
digichat attribution line added in #4130 renders instead of silently
disappearing while partially-visible Gloomberb values are shown.

In scope:

- digigraph's generic (non-retrieval) `tool_result` trace renderer
  (`digigraph/src/digigraph/workflow.py`) and its tests.
- The digichat/digiweb code paths only as **verification targets** — pinned by
  tests, not modified (see §3 decision and §7).

Out of scope: the model-facing tool message (untouched), the size caps
(unchanged), the digiquant envelope serializer (unchanged), any dashboard
surface, and every non-digifetch tool's trace payload shape.

---

## 2. Background (verified 2026-09-16, exact file:line)

### 2.1 What §7 requires

`docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md:311-321` (§7)
requires the canonical string **"Sourced from Gloomberb"** plus the delay
notice ("data delayed up to 15 minutes") wherever a Gloomberb value is
rendered outside the terminal, and deep links in the
`https://term.gloom.sh/?ticker=<SYMBOL>` form. The machine-readable block is
produced by `digiquant/src/digiquant/data/gloomberb/attribution.py`:
constants at `:21-23`, `attribution_fields(symbol)` at `:31-39` returning
exactly `attribution`, `delay_notice`, and (when a symbol is addressed)
`source_url`.

### 2.2 Where the block is appended, and when it is serialized

- `digiquant/src/digiquant/data/gloomberb/agent_tools.py:152-166`
  (`gloomberb_envelope_json`): `payload = envelope.model_dump(mode="json")`
  (`:161`), then `payload.update(attribution_fields(symbol))` (`:165`) — the §7
  keys are appended **last**, and `json.dumps(payload, indent=2, default=str)`
  (`:166`) serializes them as the final JSON keys.
- The issue cites `digiquant/src/digiquant/mcp_server.py:176-181` for this
  append. **That citation is stale.** The serializer moved to
  `data/gloomberb/agent_tools.py` in #4146 (see
  `mcp_server.py:19-29`); `mcp_server.py:176` is now R2 manifest parsing. The
  digifetch MCP tools (e.g. `mcp_server.py:896-909`) call
  `_gloomberb_envelope_json(...)`, which is the import alias of the
  `agent_tools.py` function.

### 2.3 How a digifetch result reaches digigraph

- A digichat deployment registers the digiquant MCP server with id `digiquant`
  (`cloudflare/digichat/src/lib/deploy-config/mcp-servers.test.ts:240-256`,
  asserting `dashboard-modal.yaml` declares
  `{id: "digiquant", url: "https://mcp.digithings.ai/mcp", default: true}`).
- digigraph lists its tools as extra MCP tools named
  `<server-id>_<tool>` (`orchestration/mcp_client.py:492-494`, `:514-521`,
  `:624-640`), so the model sees `digiquant_digifetch_price_history` etc.
- Calling one goes through `call_prefixed_tool` (`mcp_client.py:560-580`) →
  `_call_tool_async` (`mcp_client.py:643-669`), which returns the MCP text
  content as an **opaque string wrapper**:
  `{"ok": True, "text": "<joined text parts>"}` (`:668-669`).
- digillm forwards that dict as the `tool_result` event payload with the tool
  name merged in (`digillm/src/digillm/client.py:2168-2172`).

### 2.4 The clipper (the mechanism that loses the block)

`digigraph/src/digigraph/workflow.py`:

- `_MAX_TOOL_RESULT_CHARS = 12_000` (`:115`).
- `_clip_scalar` (`:118-126`) caps every **string scalar** at 2,000 chars
  (`:121`).
- `_clip_tool_result` (`:129-164`) recurses dicts (≤32 keys) and lists (≤50
  items) to depth 2; `rag_sources` is dropped; non-JSON-safe values become
  `None`.
- The generic `tool_result` branch (`:687-730`) builds
  `result_data = {k: v for k, v in data.items() if k != "name"}` (`:703`),
  clips it (`:704`), and — when the clipped structure still serializes to more
  than 12,000 chars — replaces it with
  `{"truncated": True, "preview": "<first ~11.9k chars>… [truncated]"}`
  (`:708-715`; fallback `:717`).

**What the code actually shows for the digifetch path:** the envelope JSON is
a *string* under `text`, so `_clip_scalar` cuts it at 2,000 chars before the
12k branch can even see a key. Because the §7 block is appended last
(`agent_tools.py:165`), it lands far beyond char 2,000 of any non-trivial
envelope (price history, statements, news lists). Small envelopes survive only
while their entire serialized form stays under 2,000 chars.

Consequence: the emitted trace result is
`{"ok": True, "text": "<first 2000 chars, no §7 keys>"}`, and no consumer can
recover the block from it. The issue's framing ("12,000-char replacement
loses the keys") names the wrong cap for this path; the operative cut is the
2,000-char scalar cap, and the 12k replacement loses keys only for
*structured* results wide enough to survive the scalar caps. Both paths are
covered by §3's fix.

### 2.5 What the renderer reads (why keys must be on the result object)

- The digichat trace adapter maps the generic `tool_result` payload's
  `result` value to the activity span's `toolResult`:
  `cloudflare/digichat/src/lib/adapters/digithings/activity/index.ts:102-128`
  (line 119: `"result" in payload ? toolResultValue(payload.result) : undefined`).
- `cloudflare/digichat/src/lib/chat-activity.ts` sanitizes the span:
  `MAX_TOOL_RESULT_CHARS = 12_000`, `MAX_TOOL_RESULT_KEYS = 32`,
  `MAX_TOOL_RESULT_ITEMS = 50` (`:39-42`); record string values are capped at
  `MAX_DOC_FIELD_CHARS = 300` (`:30`, applied at `:218-220`); a record whose
  JSON exceeds 12k is replaced by `{truncated, preview}` (`:230-234`).
- `cloudflare/digichat/src/lib/ui-stream-parts.ts:200-224` writes the
  assistant-ui tool output as `output.result = span.toolResult` (`:213`).
- The digichat thread's tool fallback calls
  `readGloomberbAttribution(result)`
  (`cloudflare/digiweb/web/src/components/chat/gallery-thread/tool-fallback.aui.tsx:315-343`,
  use at `:805`), and the helper
  (`cloudflare/digiweb/web/src/lib/gloomberb.ts:50-73`) unwraps
  `payload.result` (`:52-54`) and requires a non-blank string `attribution`
  (`:55-61`). `source_url` is kept only when it starts with the terminal URL
  (`:69`).
- #4130's own tests pin the expected shape as
  `{ result: { attribution, delay_notice, source_url } }`
  (`cloudflare/digiweb/web/src/lib/gloomberb.test.ts:36-68`;
  `cloudflare/digiweb/web/src/components/chat/digichat-thread.render.test.tsx:57-77`,
  `:380-401`).

So the §7 keys must be **top-level keys on the emitted `result` object** to
render. They cannot be reached inside a truncated `text` string: nothing in
the frontend chain parses that string, and the 300-char record-value cap would
cut it again on the digichat side anyway.

---

## 3. Approved architecture

Three options were evaluated against the code above. **The decision is option
B, restricted to the result object** — i.e. hoist the §7 block from the raw
result and attach it as top-level keys on the emitted result, ahead of the
clip.

### Option A — reorder keys before the clip (inside the envelope / clipper)

Put `attribution`, `delay_notice`, `source_url` first in the envelope dict
(digiquant `gloomberb_envelope_json`) and/or reorder dict keys in digigraph's
`_clip_tool_result`.

- **Trade-off:** smallest conceptual change, but it does not work for the
  stock path. The clipper never sees the envelope's keys — it sees
  `{"ok": true, "text": "<opaque JSON string>"}` (`mcp_client.py:668-669`) and
  cuts the string at 2,000 chars (`workflow.py:121`). Reordering keys inside
  the string changes only the string's internal order; no consumer parses the
  truncated string, and the 300-char record-value cap in
  `chat-activity.ts:218-220` cuts it again.
- **Verdict: loses.** Verified blocker (format-agnostic string truncation of
  the MCP wrapper).

### Option B (chosen) — hoist the §7 block onto the emitted result object

Before clipping, scan the **raw** result for the §7 keys — structured
envelope dicts, or the serialized envelope inside the MCP wrapper's string
value — and attach them as top-level keys of the rendered `result` object
(keys first, so a JSON reader sees provenance before the preview). The
truncation preview budget shrinks by the serialized size of the hoisted block
so the emitted record stays within the existing 12,000-char cap.

- **Trade-off:** one component (digigraph); no wire-contract additions; no
  frontend code change, because the existing chain already passes
  `payload.result` through unchanged
  (`activity/index.ts:119`, `ui-stream-parts.ts:213`) and the #4130 renderer
  already reads top-level keys off that object (`gloomberb.ts:50-73`). The
  keys ride on the same object the JSON result pane already shows. Cost: one
  bounded extraction per generic tool result, and a preview that is ~150
  chars shorter when the block is present (the 12k cap itself is unchanged).
- **Verdict: wins.** Smallest blast radius that provably renders.

### Option C — lift attribution from the raw trace payload in the digichat adapter

Read the §7 keys from the pre-clip payload inside
`activity/index.ts`.

- **Trade-off:** impossible as written. The adapter only ever sees digigraph's
  already-clipped payload (`workflow.py:703-718`); the raw envelope is gone
  before digichat receives anything. Making it possible would require
  digigraph to emit the raw payload alongside the clipped one — more data on
  the wire than option B, with the same frontend reading problem.
- **Verdict: loses.**

### Rejected sub-variant of B: a separate top-level trace field

Emitting `payload["attribution"] = {...}` (a sibling of `result`) and mapping
it in the adapter would require changes in
`activity/index.ts` (span field), `chat-activity.ts` (sanitizer allowlist),
`ui-stream-parts.ts` (part output), and the renderer — four files to reach the
same rendering, plus a new span contract. Strictly more surface for the same
outcome. **Loses to result-level hoisting.**

### Chosen design, concretely

In `workflow.py`, next to the existing clipper:

- `_ATTRIBUTION_KEYS = ("attribution", "delay_notice", "source_url")`.
- `_extract_attribution(value) -> dict[str, str]`: bounded walk (depth ≤ 3,
  ≤ 64 values per mapping/sequence) over dicts/lists; a string is parsed only
  when it contains the substring `"attribution"` (cheap guard), and malformed
  JSON is skipped, never raised.
- `_render_clipped_tool_result(result_data) -> Any | None`: performs the
  current clip + 12k-truncation logic, then prepends the extracted block
  (`{**attribution, **rendered}`) when the rendered value is a dict.

The generic branch (`workflow.py:703-718`) collapses to
`rendered = _render_clipped_tool_result(result_data)`.

The extraction is **key-based, not vendor-based**: it looks for the §7 key
names wherever they appear in a result, so digigraph stays vendor-neutral and
does not import digiquant code (which the component rules forbid). The keys
are copied verbatim; absent keys are not synthesized.

---

## 4. Contracts (load-bearing)

**Trace contract (digigraph → digichat), unchanged except where noted.** A
generic `tool_result` trace payload keeps: `tool`, `status` (`failed` /
`completed`), optional `arguments` (queued clipped args), optional `query`,
and `result`. Source of truth:
`digigraph/src/digigraph/ARCHITECTURE.md:118-132`.

**Rendered `result` object — new guarantee.** When the raw result carries any
of the §7 keys, the emitted `result` object carries them as top-level string
keys, inserted before the clipped fields:

```json
{
  "attribution": "Sourced from Gloomberb",
  "delay_notice": "Data delayed up to 15 minutes",
  "source_url": "https://term.gloom.sh/?ticker=AAPL",
  "ok": true,
  "text": "<first 2000 chars of the envelope>"
}
```

and for a >12k structured result:

```json
{
  "attribution": "Sourced from Gloomberb",
  "delay_notice": "Data delayed up to 15 minutes",
  "source_url": "https://term.gloom.sh/?ticker=AAPL",
  "truncated": true,
  "preview": "<first ~11.7k chars of the clipped JSON>… [truncated]"
}
```

- Key names are exactly the `attribution.py:34-38` names. Values are copied
  verbatim; a key whose raw value is absent or not a non-blank string is
  omitted.
- The result remains JSON-serializable (same `_clip_tool_result` guarantees).
- `source_url` is passed through without validation; the terminal-origin guard
  stays frontend-side (`gloomberb.ts:69`).
- No other trace payload key is added, renamed, or removed.

**Renderer input contract (unchanged).** `readGloomberbAttribution` receives
the assistant-ui tool output (`output.result`), unwraps `payload.result`, and
requires a top-level `attribution` string. The rendered object above satisfies
it with no frontend change. The digichat adapter/span passthrough
(`activity/index.ts:119`) and the sanitizer caps
(`chat-activity.ts:30,39-42,218-220,230-234`) are unchanged.

**Model-facing payload (untouched).** `_render_clipped_tool_result` only
builds the trace payload; the tool message the model sees is assembled
separately from the raw result (`digillm/src/digillm/client.py:2173-2179`).

---

## 5. Normative values

| Item | Value | Where |
|---|---|---|
| Trace attribution keys | `("attribution", "delay_notice", "source_url")` | new constant, verbatim from `attribution.py:34-38` |
| Scalar string cap | 2,000 chars (unchanged) | `workflow.py:121` |
| Total record cap | 12,000 chars (unchanged) | `workflow.py:115` |
| Truncation marker | `"… [truncated]"` (unchanged) | `workflow.py:714` |
| Truncation preview budget | `12_000 - 100 - len(json.dumps(attribution))`; `12_000 - 100` when no block is present | new, same cap |
| Extraction walk depth / breadth | 3 levels / 64 values per mapping or sequence | new |
| JSON-parse guard | parse a string only when `'"attribution"' in value` | new |
| Digichat record value cap | 300 chars (unchanged) | `chat-activity.ts:30,220` |
| Digichat record cap | 12,000 chars (unchanged) | `chat-activity.ts:40` |

The preview budget accounts for the hoisted block so the emitted record never
exceeds 12,000 chars — otherwise digichat's sanitizer
(`chat-activity.ts:230-234`) would replace the whole record with a
`{truncated, preview}` pair and drop the keys.

---

## 6. Rollout order

1. **digigraph fix + tests + ARCHITECTURE note** — branch `task/4131-…` cut
   from a current `origin/module/digigraph` (`component:digigraph` routes
   `task → module/digigraph → develop` per `scripts/project_routing.json`).
   PR body carries `Fixes #4131`. The frontend works untouched the moment
   this merges.
2. **digiweb renderer pin** (`component:website`, one-hop → `develop`):
   test-only addition to `digichat-thread.render.test.tsx`; can merge any time
   after or independently of step 1 (it pins the shape step 1 emits).
3. **digichat adapter pin** (`component:digichat` → `module/digichat`):
   test-only addition to `tool-result.test.ts`; same independence.
4. No flags, no migrations, no serialized-state concerns; rollback is a revert
   of step 1 alone (the extra keys are additive and ignored by older
   clients).

Steps 2–3 are verification pins, not prerequisites for the fix.

---

## 7. Verification (measurable)

All commands run from the repo root of the relevant worktree.

**digigraph (the fix).**

- `pytest tests/dg/test_tool_result_attribution.py -v` — the end-to-end trace
  test drives `run_digigraph_workflow_streaming` with a fake graph (the
  `tests/dg/test_boundaries.py:79-116` harness shape) whose stream yields the
  real `{"name": "digiquant_digifetch_price_history", "ok": True, "text":
  "<envelope serialized with the §7 block last>"}` payload and asserts the
  emitted trace `result` carries all three keys, the `text` scalar is still
  cut at 2,000 chars, and the whole record is ≤ 12,000 chars. Before the fix
  this fails with `KeyError: 'attribution'`; after, it passes.
- `pytest -m unit tests/dg/ -q` — no digigraph regression.
- `ruff check digigraph/ && ruff format --check digigraph/` — clean.

**digiweb (renderer pin).**
`npm --workspace @digithings/web run test -- src/components/chat/digichat-thread.render.test.tsx`
— the new case renders a clipped-but-attributed result and asserts
"Sourced from Gloomberb", the delay notice, and the
`https://term.gloom.sh/?ticker=AAPL` anchor.

**digichat (adapter pin).**
`npm run test --workspace digichat -- src/lib/adapters/digithings/activity/tool-result.test.ts`
— asserts the §7 keys survive `mapDigigraphTraceToSpans` (which runs the
`chat-activity.ts` sanitizer) on a result whose `text` exceeds the 300-char
record-value cap.

Success = all three green plus the digigraph suite unchanged.

---

## 8. Risks and fallbacks

- **Front-side re-truncation.** If the emitted record exceeds 12,000 chars,
  `chat-activity.ts:230-234` replaces it with `{truncated, preview}` and the
  keys vanish. Mitigated by the preview budget in §5; the plan pins the total
  with an assertion. If a future cap change breaks the budget, the fallback is
  to shorten the preview further (the cap is on the record, not the preview).
- **Parse cost.** Extraction parses a string only when it contains
  `"attribution"`; Digifetch envelopes append the block last, so large
  payloads pay one `json.loads` of an already-serialized string. If that ever
  profiles badly, the fallback is a bounded tail regex over the last ~1 KB,
  accepting the same key names. Not warranted now.
- **Non-dict results.** A bare string or list result cannot carry sibling
  keys; the block is dropped there exactly as today. No current
  MCP-digifetch path produces that shape (the wrapper is a dict).
- **False positives.** `attribution`/`delay_notice`/`source_url` on an
  unrelated tool result would be hoisted — harmless (they are truthful
  payload data and the renderer already keys on `attribution` alone). No
  vendor check is added, keeping digigraph free of digiquant imports.
- **Preview shrink.** ~150 fewer preview chars on attributed payloads only;
  no cap semantics change.
- **Caps and model context.** The model-facing text and the 12k/2k caps are
  untouched, so the fix cannot enlarge what the model or the UI receives.

---

## 9. Out of scope

- Reordering the digiquant envelope serializer (`agent_tools.py`) — not
  needed and not sufficient (option A).
- A new separate trace field/part (the rejected B sub-variant) and any
  adapter/span/part plumbing change.
- Changing any size cap, the 300-char digichat record-value cap, or the
  truncation marker.
- The dashboard "Open in Gloomberb" link-out (#4130) and any other surface.
- Attribution for non-Gloomberb tools, digisearch/`rag_sources` payloads, or
  the model-facing tool message.

---

## 10. Open questions (for spec review, not implementation)

1. **"Small envelopes render correctly today" could not be reproduced from
   code.** The issue states quote/news envelopes render attribution today; the
   code shows the §7 block inside the MCP wrapper's `text` string, which
   neither `readGloomberbAttribution` parses nor the 300-char record cap
   preserves beyond the first ~300 chars. The chosen fix makes *all* sizes
   render (it hoists the block whenever it is present), so this does not
   change the decision — but if a live probe shows a path that works today,
   the verification steps should record it rather than assume it.
2. Should the digichat adapter test also assert the 300-char `text` cap
   explicitly (brittle if the constant moves), or only that the keys survive?
   The plan pins survival plus a loose `<2000` bound.
3. Preview budget derivation: `12_000 - 100 - len(json.dumps(attribution))`
   keeps today's 100-char slack. If the hoisted block ever grows, the record
   stays under the cap by construction; confirm this is preferred over fixing
   the preview at a constant and letting the record exceed 12k.
