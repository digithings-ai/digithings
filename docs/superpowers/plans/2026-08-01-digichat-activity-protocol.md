# DigiChat Activity Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace DigiChat's single `data-digigraphTrace{label,status}` data-part with an OpenTelemetry GenAI-named activity vocabulary, so every backend provider can feed the four richer activity kinds the shared UI already renders.

**Architecture:** One new module (`src/lib/chat-activity.ts`) owns the `ActivitySpan` type, a server-side allowlist/detail gate, and the client-side projection onto `@digithings/digichat-ui`'s `DigiChatActivity` union. Providers write `data-digichatActivity`; the client reads it and falls back to the legacy trace part for one release. Tasks are ordered so the client understands both shapes *before* any provider switches — there is no commit at which activities stop rendering.

**Tech Stack:** TypeScript, Next.js 16, Vercel AI SDK (`ai@6.0.168`), Vitest.

## Global Constraints

- All work is inside `frontend/digichat`. Do not modify `@digithings/digichat-ui`, `datatap-web`, or `digithings-web`.
- `ActivitySpan` **is** the disclosure allowlist. Never add a field for an upstream endpoint, model id, raw prompt, or upstream error body.
- Field names follow OpenTelemetry GenAI semantic conventions: `operation` is `gen_ai.operation.name`, `toolName` is `gen_ai.tool.name`.
- Do **not** wire an OTLP exporter, tracer provider, or `experimental_telemetry` in this phase. No `OTEL_EXPORTER_OTLP_ENDPOINT` is configured anywhere in the repo.
- Import `DigiChatActivity` with `import type` only — `chat-activity.ts` is imported by server modules and must not pull React components into the server bundle.
- Detail default: **embed tenants** that do not specify `activityDetail` get `"labels"`. The **authenticated (non-embed) app path** uses `"full"` — the allowlist exists to protect anonymous public embeds, not signed-in users.
- Run tests from `frontend/digichat` with `npx vitest run <path>`.
- Spec: `docs/superpowers/specs/2026-08-01-digichat-activity-protocol-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/lib/chat-activity.ts` (create) | The activity vocabulary: `ActivitySpan`, sanitizer/allowlist, detail gate, client projector |
| `src/lib/chat-activity.test.ts` (create) | Tests for all of the above |
| `src/hooks/use-embed-digi-chat.ts` (modify) | Read the new part; keep legacy trace fallback |
| `src/lib/embed-tenants.ts` (modify) | `activityDetail` tenant config |
| `src/lib/foundry-stream.ts` (modify) | Emit spans instead of traces |
| `src/lib/external-relay-stream.ts` (modify) | Emit spans instead of traces |
| `src/lib/stream-digigraph-trace.ts` (modify) | Emit spans; stop leaking upstream error bodies |
| `src/app/api/chat/route.ts` (modify) | Pass `activityDetail` to each provider |

---

### Task 1: The activity vocabulary

**Files:**
- Create: `frontend/digichat/src/lib/chat-activity.ts`
- Test: `frontend/digichat/src/lib/chat-activity.test.ts`

**Interfaces:**
- Consumes: `DigiChatActivity` (type only) from `@digithings/digichat-ui`
- Produces:
  - `const ACTIVITY_PART_TYPE = "data-digichatActivity"`
  - `type ActivityDetail = "off" | "labels" | "full"`
  - `type ActivityDocument = { title: string; path: string }`
  - `type ActivitySpan = { operation: "execute_tool" | "retrieve" | "chat"; toolName?: string; query?: string; status: "started" | "completed" | "failed"; label: string; documents?: ActivityDocument[]; reasoningDelta?: string }`
  - `function sanitizeActivitySpan(input: unknown): ActivitySpan | null`
  - `function applyActivityDetail(span: ActivitySpan, detail: ActivityDetail): ActivitySpan | null`

- [ ] **Step 1: Write the failing tests**

Create `frontend/digichat/src/lib/chat-activity.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  sanitizeActivitySpan,
  applyActivityDetail,
  MAX_LABEL_CHARS,
  MAX_DOCUMENTS,
  type ActivitySpan,
} from "./chat-activity";

const span = (extra: Record<string, unknown> = {}): Record<string, unknown> => ({
  operation: "execute_tool",
  status: "started",
  label: "Searching knowledge base…",
  ...extra,
});

describe("sanitizeActivitySpan", () => {
  it("keeps every declared field", () => {
    expect(
      sanitizeActivitySpan(
        span({
          status: "completed",
          operation: "retrieve",
          toolName: "file_search",
          query: "auth",
          documents: [{ title: "Auth", path: "https://x/auth" }],
          reasoningDelta: "thinking",
        })
      )
    ).toEqual({
      operation: "retrieve",
      status: "completed",
      label: "Searching knowledge base…",
      toolName: "file_search",
      query: "auth",
      documents: [{ title: "Auth", path: "https://x/auth" }],
      reasoningDelta: "thinking",
    });
  });

  // The disclosure boundary: this type IS the allowlist, so anything a provider
  // did not mean to publish must not survive projection onto the public embed.
  it("drops undeclared keys rather than passing them through", () => {
    const out = sanitizeActivitySpan(
      span({
        projectEndpoint: "https://internal.foundry.azure.com",
        "gen_ai.request.model": "gpt-4o",
        prompt: "the user's private question",
        upstreamError: "Traceback (most recent call last)…",
      })
    );
    expect(out).not.toBeNull();
    expect(Object.keys(out!).sort()).toEqual(["label", "operation", "status"]);
  });

  it("rejects an unknown operation or status", () => {
    expect(sanitizeActivitySpan(span({ operation: "exfiltrate" }))).toBeNull();
    expect(sanitizeActivitySpan(span({ status: "maybe" }))).toBeNull();
  });

  it("rejects non-object input", () => {
    expect(sanitizeActivitySpan(null)).toBeNull();
    expect(sanitizeActivitySpan("started")).toBeNull();
    expect(sanitizeActivitySpan([span()])).toBeNull();
  });

  it("truncates an over-long label and caps the document list", () => {
    const out = sanitizeActivitySpan(
      span({
        label: "x".repeat(MAX_LABEL_CHARS + 50),
        documents: Array.from({ length: MAX_DOCUMENTS + 5 }, (_, i) => ({
          title: `t${i}`,
          path: `p${i}`,
        })),
      })
    );
    expect(out!.label).toHaveLength(MAX_LABEL_CHARS);
    expect(out!.documents).toHaveLength(MAX_DOCUMENTS);
  });

  it("drops malformed documents without dropping the span", () => {
    const out = sanitizeActivitySpan(
      span({ documents: [{ title: "ok", path: "p" }, { title: 42 }, null, "nope"] })
    );
    expect(out!.documents).toEqual([{ title: "ok", path: "p" }]);
  });

  it("omits documents entirely when none survive", () => {
    const out = sanitizeActivitySpan(span({ documents: [null, "nope"] }));
    expect(out).not.toBeNull();
    expect("documents" in out!).toBe(false);
  });
});

describe("applyActivityDetail", () => {
  const full: ActivitySpan = {
    operation: "retrieve",
    status: "completed",
    label: "Sources",
    toolName: "file_search",
    query: "auth",
    documents: [{ title: "Auth", path: "https://x/auth" }],
    reasoningDelta: "thinking",
  };

  it("emits nothing at all when detail is off", () => {
    expect(applyActivityDetail(full, "off")).toBeNull();
  });

  // Server-side gate: "labels" tenants must never receive documents over the
  // wire. This is not CSS hiding.
  it("strips documents and reasoning at labels", () => {
    const out = applyActivityDetail(full, "labels")!;
    expect(out.documents).toBeUndefined();
    expect(out.reasoningDelta).toBeUndefined();
    expect(out.label).toBe("Sources");
    expect(out.query).toBe("auth");
  });

  it("passes everything through at full", () => {
    expect(applyActivityDetail(full, "full")).toEqual(full);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend/digichat && npx vitest run src/lib/chat-activity.test.ts`
Expected: FAIL — `Failed to resolve import "./chat-activity"`

- [ ] **Step 3: Write the implementation**

Create `frontend/digichat/src/lib/chat-activity.ts`:

```ts
/**
 * DigiChat activity protocol — the vocabulary every backend provider emits and
 * the shared UI renders.
 *
 * Field names follow OpenTelemetry GenAI semantic conventions (`operation` is
 * gen_ai.operation.name, `toolName` is gen_ai.tool.name) so these same events can
 * later feed a real OTLP exporter without inventing a second vocabulary. The
 * exporter itself is deliberately out of scope for this phase — no collector is
 * configured anywhere in the repo yet.
 *
 * IMPORTANT: this type IS the disclosure allowlist. It has no field for an
 * upstream endpoint, model id, raw prompt, or upstream error body, so a provider
 * cannot leak internals to a public anonymous embed by accident. Anything worth
 * surfacing must pass through a declared field.
 *
 * Spec: docs/superpowers/specs/2026-08-01-digichat-activity-protocol-design.md
 */

export const ACTIVITY_PART_TYPE = "data-digichatActivity" as const;

export const MAX_LABEL_CHARS = 200;
export const MAX_QUERY_CHARS = 200;
export const MAX_DOCUMENTS = 8;
export const MAX_DOC_FIELD_CHARS = 300;
export const MAX_REASONING_CHARS = 4000;

export type ActivityDetail = "off" | "labels" | "full";

export type ActivityDocument = { title: string; path: string };

export type ActivitySpan = {
  /** gen_ai.operation.name */
  operation: "execute_tool" | "retrieve" | "chat";
  /** gen_ai.tool.name */
  toolName?: string;
  query?: string;
  status: "started" | "completed" | "failed";
  /** Presentation-safe; never raw upstream text. */
  label: string;
  documents?: ActivityDocument[];
  reasoningDelta?: string;
};

const OPERATIONS = ["execute_tool", "retrieve", "chat"] as const;
const STATUSES = ["started", "completed", "failed"] as const;

function str(value: unknown, max: number): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed.slice(0, max);
}

function documents(value: unknown): ActivityDocument[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: ActivityDocument[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const record = entry as Record<string, unknown>;
    const title = str(record.title, MAX_DOC_FIELD_CHARS);
    const path = str(record.path, MAX_DOC_FIELD_CHARS);
    if (!title || !path) continue;
    out.push({ title, path });
    if (out.length === MAX_DOCUMENTS) break;
  }
  return out.length ? out : undefined;
}

/**
 * Rebuilds a span from scratch out of declared fields only. Undeclared keys are
 * not stripped so much as never copied — that is what makes this an allowlist
 * rather than a denylist that a new provider field could slip past.
 */
export function sanitizeActivitySpan(input: unknown): ActivitySpan | null {
  if (!input || typeof input !== "object" || Array.isArray(input)) return null;
  const record = input as Record<string, unknown>;

  const operation = OPERATIONS.find((o) => o === record.operation);
  const status = STATUSES.find((s) => s === record.status);
  const label = str(record.label, MAX_LABEL_CHARS);
  if (!operation || !status || !label) return null;

  const span: ActivitySpan = { operation, status, label };

  const toolName = str(record.toolName, MAX_LABEL_CHARS);
  if (toolName) span.toolName = toolName;

  const query = str(record.query, MAX_QUERY_CHARS);
  if (query) span.query = query;

  const docs = documents(record.documents);
  if (docs) span.documents = docs;

  const reasoningDelta = str(record.reasoningDelta, MAX_REASONING_CHARS);
  if (reasoningDelta) span.reasoningDelta = reasoningDelta;

  return span;
}

/**
 * Server-side detail gate. Applied before the span is written to the stream, so
 * `off` and `labels` tenants never receive documents or reasoning over the wire.
 */
export function applyActivityDetail(
  span: ActivitySpan,
  detail: ActivityDetail
): ActivitySpan | null {
  if (detail === "off") return null;
  if (detail === "full") return span;
  const { documents: _documents, reasoningDelta: _reasoning, ...rest } = span;
  void _documents;
  void _reasoning;
  return rest;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/chat-activity.test.ts`
Expected: PASS — 10 tests

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/chat-activity.ts frontend/digichat/src/lib/chat-activity.test.ts
git commit -m "feat(digichat): add the gen_ai-named activity span vocabulary"
```

---

### Task 2: Project spans onto the shared UI union

**Files:**
- Modify: `frontend/digichat/src/lib/chat-activity.ts`
- Test: `frontend/digichat/src/lib/chat-activity.test.ts`

**Interfaces:**
- Consumes: `ActivitySpan` from Task 1
- Produces: `function toDigiChatActivity(spans: ActivitySpan[]): DigiChatActivity[]`

Behaviour this must implement, from the spec:
- Foundry emits the search step and the citations as **two** spans; they merge into **one** `tool_result` row.
- A completed search that produced no citations becomes a **"no hits"** row (`tool_result`, `count: 0`), not a bare `tool_call`.
- A search still in flight stays a `tool_call`.
- Dedupe keys on `(toolName, query)` — two different searches must not merge just because their labels match.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/digichat/src/lib/chat-activity.test.ts`:

```ts
import { toDigiChatActivity } from "./chat-activity";

const started = (toolName: string, query?: string): ActivitySpan => ({
  operation: "execute_tool",
  toolName,
  status: "started",
  label: "Searching knowledge base…",
  ...(query ? { query } : {}),
});

const finished = (toolName: string, query: string): ActivitySpan => ({
  operation: "execute_tool",
  toolName,
  query,
  status: "completed",
  label: `Searched for: "${query}"`,
});

const retrieved = (
  toolName: string,
  query: string,
  docs: { title: string; path: string }[]
): ActivitySpan => ({
  operation: "retrieve",
  toolName,
  query,
  status: "completed",
  label: "Sources",
  documents: docs,
});

describe("toDigiChatActivity", () => {
  it("returns no rows for no spans", () => {
    expect(toDigiChatActivity([])).toEqual([]);
  });

  // The Foundry shape: three spans across two events collapse to one result row.
  it("merges the search and its citations into a single tool_result", () => {
    const rows = toDigiChatActivity([
      started("file_search"),
      finished("file_search", "auth"),
      retrieved("file_search", "auth", [{ title: "Auth", path: "https://x/auth" }]),
    ]);
    expect(rows).toEqual([
      {
        kind: "tool_result",
        name: "file_search",
        query: "auth",
        hits: [{ title: "Auth", path: "https://x/auth" }],
        count: 1,
      },
    ]);
  });

  it("renders an in-flight search as a tool_call", () => {
    expect(toDigiChatActivity([started("file_search")])).toEqual([
      { kind: "tool_call", name: "file_search", query: "" },
    ]);
  });

  it("renders a completed search with no citations as a no-hits result", () => {
    expect(toDigiChatActivity([started("file_search"), finished("file_search", "auth")])).toEqual([
      { kind: "tool_result", name: "file_search", query: "auth", hits: [], count: 0 },
    ]);
  });

  it("keeps two different queries as separate rows", () => {
    const rows = toDigiChatActivity([
      finished("file_search", "auth"),
      retrieved("file_search", "auth", [{ title: "A", path: "a" }]),
      finished("file_search", "billing"),
      retrieved("file_search", "billing", [{ title: "B", path: "b" }]),
    ]);
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => (r.kind === "tool_result" ? r.query : null))).toEqual([
      "auth",
      "billing",
    ]);
  });

  it("collapses repeated chat traces by label and ORs their done flag", () => {
    const trace = (label: string, status: ActivitySpan["status"]): ActivitySpan => ({
      operation: "chat",
      status,
      label,
    });
    expect(
      toDigiChatActivity([trace("Planning", "started"), trace("Planning", "completed")])
    ).toEqual([{ kind: "trace", label: "Planning", done: true }]);
  });

  it("accumulates reasoning deltas into one trailing block", () => {
    const reason = (text: string): ActivitySpan => ({
      operation: "chat",
      status: "started",
      label: "reasoning",
      reasoningDelta: text,
    });
    expect(toDigiChatActivity([reason("one "), reason("two")])).toEqual([
      { kind: "reasoning", text: "one two" },
    ]);
  });

  // "failed" is terminal: the row must settle, not spin forever.
  it("settles a failed step rather than leaving it pending", () => {
    expect(
      toDigiChatActivity([{ operation: "chat", status: "failed", label: "Planning" }])
    ).toEqual([{ kind: "trace", label: "Planning", done: true }]);
    expect(
      toDigiChatActivity([
        started("file_search"),
        { ...finished("file_search", "auth"), status: "failed" },
      ])
    ).toEqual([{ kind: "tool_result", name: "file_search", query: "auth", hits: [], count: 0 }]);
  });

  it("renders citations with no preceding search step using an empty query", () => {
    expect(
      toDigiChatActivity([
        { operation: "retrieve", status: "completed", label: "Sources", documents: [{ title: "A", path: "a" }] },
      ])
    ).toEqual([{ kind: "tool_result", name: "search", query: "", hits: [{ title: "A", path: "a" }], count: 1 }]);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend/digichat && npx vitest run src/lib/chat-activity.test.ts`
Expected: FAIL — `toDigiChatActivity is not a function`

- [ ] **Step 3: Write the implementation**

Add to the top of `frontend/digichat/src/lib/chat-activity.ts`, below the existing header comment:

```ts
import type { DigiChatActivity } from "@digithings/digichat-ui";
```

Append to the end of the same file:

```ts
const KEY_SEP = " ";
const toolKey = (name: string, query: string) => `${name}${KEY_SEP}${query}`;

/**
 * Projects provider spans onto the union the shared UI renders.
 *
 * Called over the whole span list on each render (not incrementally), which is
 * what lets the trailing pass rewrite a finished-but-empty search into a
 * "no hits" row: whether citations followed is only knowable once the list ends.
 */
export function toDigiChatActivity(spans: ActivitySpan[]): DigiChatActivity[] {
  const rows: DigiChatActivity[] = [];
  const toolRows = new Map<string, number>();
  const traceRows = new Map<string, number>();
  const completedTools = new Set<string>();
  let pendingTool = "search";
  let pendingQuery = "";
  let reasoning = "";

  for (const span of spans) {
    if (span.reasoningDelta) {
      reasoning += span.reasoningDelta;
      continue;
    }

    if (span.operation === "execute_tool") {
      const name = span.toolName ?? "tool";
      pendingTool = name;
      if (span.query) pendingQuery = span.query;

      const key = toolKey(name, span.query ?? "");
      // "failed" is terminal too — a search that errored must not render as a
      // tool call that never finishes.
      if (span.status !== "started") completedTools.add(key);
      if (toolRows.has(key)) continue;

      // A "started" span has no query yet, so it keys on the empty string; the
      // later "completed" span carries the query and upgrades that row in place
      // rather than opening a second one for the same search.
      const blank = toolKey(name, "");
      const blankIdx = toolRows.get(blank);
      if (blankIdx !== undefined && span.query) {
        const row = rows[blankIdx];
        if (row.kind === "tool_call") row.query = span.query;
        toolRows.delete(blank);
        toolRows.set(key, blankIdx);
        completedTools.delete(blank);
        continue;
      }

      rows.push({ kind: "tool_call", name, query: span.query ?? "" });
      toolRows.set(key, rows.length - 1);
      continue;
    }

    if (span.operation === "retrieve") {
      const name = span.toolName ?? pendingTool ?? "search";
      const query = span.query ?? pendingQuery;
      const hits = span.documents ?? [];
      const key = toolKey(name, query);
      const result: DigiChatActivity = {
        kind: "tool_result",
        name,
        query,
        hits,
        count: hits.length,
      };
      const idx = toolRows.get(key);
      if (idx !== undefined) {
        rows[idx] = result;
      } else {
        rows.push(result);
        toolRows.set(key, rows.length - 1);
      }
      completedTools.delete(key);
      continue;
    }

    // operation === "chat": an opaque upstream step. Collapse by label so a
    // provider re-emitting the same step does not stack duplicate rows.
    const key = span.label;
    const done = span.status !== "started";
    const idx = traceRows.get(key);
    if (idx !== undefined) {
      const row = rows[idx];
      if (row.kind === "trace") row.done = row.done || done;
      continue;
    }
    rows.push({ kind: "trace", label: span.label, done });
    traceRows.set(key, rows.length - 1);
  }

  // A search that completed and never produced citations is a "no hits" answer,
  // not a perpetually-pending tool call.
  for (const [key, idx] of toolRows) {
    const row = rows[idx];
    if (row.kind === "tool_call" && completedTools.has(key)) {
      rows[idx] = { kind: "tool_result", name: row.name, query: row.query, hits: [], count: 0 };
    }
  }

  if (reasoning) rows.push({ kind: "reasoning", text: reasoning });
  return rows;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/chat-activity.test.ts`
Expected: PASS — 19 tests

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/chat-activity.ts frontend/digichat/src/lib/chat-activity.test.ts
git commit -m "feat(digichat): project activity spans onto the shared UI union"
```

---

### Task 3: Client reads the new part, keeps the legacy fallback

**Files:**
- Modify: `frontend/digichat/src/hooks/use-embed-digi-chat.ts:34-69`
- Test: `frontend/digichat/src/hooks/use-embed-digi-chat.test.ts`

**Interfaces:**
- Consumes: `ACTIVITY_PART_TYPE`, `sanitizeActivitySpan`, `toDigiChatActivity` from Tasks 1–2
- Produces: `uiMessageToDigiChat(message: UIMessage): DigiChatMessage` — unchanged signature

Client and server ship in the same container image, so the legacy `data-digigraphTrace` branch only covers iframe pages a visitor had cached across a deploy. It is removed one release later, not here.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/digichat/src/hooks/use-embed-digi-chat.test.ts`:

```ts
import { ACTIVITY_PART_TYPE } from "@/lib/chat-activity";

const activityPart = (data: unknown) => ({ type: ACTIVITY_PART_TYPE, data });

describe("uiMessageToDigiChat activity parts", () => {
  it("projects activity spans into rich rows", () => {
    const msg = {
      id: "a1",
      role: "assistant",
      parts: [
        { type: "text", text: "Here you go." },
        activityPart({
          operation: "retrieve",
          toolName: "file_search",
          query: "auth",
          status: "completed",
          label: "Sources",
          documents: [{ title: "Auth", path: "https://x/auth" }],
        }),
      ],
    } as unknown as UIMessage;

    expect(uiMessageToDigiChat(msg)).toEqual({
      role: "assistant",
      content: "Here you go.",
      activities: [
        {
          kind: "tool_result",
          name: "file_search",
          query: "auth",
          hits: [{ title: "Auth", path: "https://x/auth" }],
          count: 1,
        },
      ],
    });
  });

  // The allowlist has to hold at the client boundary too, not only at the writer.
  it("drops a malformed span rather than rendering it", () => {
    const msg = {
      id: "a2",
      role: "assistant",
      parts: [{ type: "text", text: "hi" }, activityPart({ operation: "exfiltrate" })],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toBeUndefined();
  });

  // Compatibility window: a page cached across a deploy still speaks the old part.
  it("still renders a legacy digigraphTrace part when no activity parts are present", () => {
    const msg = {
      id: "a3",
      role: "assistant",
      parts: [
        { type: "text", text: "hi" },
        {
          type: "data-digigraphTrace",
          data: { v: 1, type: "external_activity", payload: { label: "Planning", status: "completed" } },
        },
      ],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toEqual([
      { kind: "trace", label: "Planning", done: true },
    ]);
  });

  // Activity parts win outright — a mid-stream deploy must not double-render.
  it("ignores legacy trace parts when activity parts are present", () => {
    const msg = {
      id: "a4",
      role: "assistant",
      parts: [
        { type: "text", text: "hi" },
        activityPart({ operation: "chat", status: "completed", label: "New" }),
        {
          type: "data-digigraphTrace",
          data: { v: 1, type: "external_activity", payload: { label: "Old", status: "completed" } },
        },
      ],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toEqual([
      { kind: "trace", label: "New", done: true },
    ]);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend/digichat && npx vitest run src/hooks/use-embed-digi-chat.test.ts`
Expected: FAIL — the first new test reports `activities: undefined`

- [ ] **Step 3: Rewrite `uiMessageToDigiChat`**

In `frontend/digichat/src/hooks/use-embed-digi-chat.ts`, add to the imports:

```ts
import {
  ACTIVITY_PART_TYPE,
  sanitizeActivitySpan,
  toDigiChatActivity,
  type ActivitySpan,
} from "@/lib/chat-activity";
```

Replace the whole body of `uiMessageToDigiChat` (currently lines 34–69) with:

```ts
/**
 * Legacy path: providers emitted a single data-digigraphTrace{label,status} part
 * before the activity protocol landed. Kept for one release so an iframe page a
 * visitor cached across a deploy still renders its steps.
 */
function legacyTraceActivities(message: UIMessage): DigiChatActivity[] {
  const traces = message.parts.filter(
    (part): part is { type: "data-digigraphTrace"; data: TracePartData } =>
      part.type === "data-digigraphTrace"
  );

  // Collapse trace steps by label: the external relay can emit the same step
  // more than once (e.g. repeated "in_progress" frames), and each trace part
  // carries a unique id so nothing reconciles upstream. Keyed by resolved
  // label, first-seen order preserved; `done` is true if any frame completed.
  const byLabel = new Map<string, { label: string; done: boolean }>();
  for (const t of traces) {
    const label = String(t.data?.payload?.label ?? t.data?.type ?? "activity");
    const done = t.data?.payload?.status === "completed";
    const seen = byLabel.get(label);
    if (seen) seen.done = seen.done || done;
    else byLabel.set(label, { label, done });
  }

  return Array.from(byLabel.values(), (t) => ({
    kind: "trace" as const,
    label: t.label,
    done: t.done,
  }));
}

export function uiMessageToDigiChat(message: UIMessage): DigiChatMessage {
  const text = message.parts
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("");

  const spans = message.parts
    .filter((part): part is { type: typeof ACTIVITY_PART_TYPE; data: unknown } =>
      part.type === ACTIVITY_PART_TYPE
    )
    .map((part) => sanitizeActivitySpan(part.data))
    .filter((span): span is ActivitySpan => span !== null);

  // Activity parts win outright: during a deploy a single message could carry
  // both shapes, and rendering both would double every step.
  const hasActivityParts = message.parts.some((part) => part.type === ACTIVITY_PART_TYPE);
  const activities = hasActivityParts
    ? toDigiChatActivity(spans)
    : legacyTraceActivities(message);

  return {
    role: message.role === "user" ? "user" : "assistant",
    content: text,
    activities: activities.length ? activities : undefined,
  };
}
```

- [ ] **Step 4: Run the full hook test file**

Run: `cd frontend/digichat && npx vitest run src/hooks/use-embed-digi-chat.test.ts`
Expected: PASS — pre-existing tests plus the 4 new ones

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/hooks/use-embed-digi-chat.ts frontend/digichat/src/hooks/use-embed-digi-chat.test.ts
git commit -m "feat(digichat): read activity parts on the client with a legacy trace fallback"
```

---

### Task 4: `activityDetail` tenant config

**Files:**
- Modify: `frontend/digichat/src/lib/embed-tenants.ts:16-49` (type), `:121-124` (validation), `:172-186` (return)
- Test: `frontend/digichat/src/lib/embed-tenants.test.ts`

**Interfaces:**
- Consumes: `ActivityDetail` from Task 1
- Produces: `EmbedTenantConfig.activityDetail: ActivityDetail` — always populated, defaulting to `"labels"`

- [ ] **Step 1: Write the failing tests**

Append to `frontend/digichat/src/lib/embed-tenants.test.ts`:

```ts
describe("activityDetail", () => {
  const entry = (extra: Record<string, unknown> = {}) =>
    JSON.stringify({
      "tenant.example": {
        slug: "tenant",
        backend: { type: "digigraph" },
        gateMode: "ungated",
        token: "tok",
        ...extra,
      },
    });

  // Conservative by construction: a tenant nobody configured must not stream
  // retrieved document titles to anonymous visitors.
  it("defaults to labels when unspecified", () => {
    const cfg = parseEmbedTenants(entry()).get("tenant.example")!;
    expect(cfg.activityDetail).toBe("labels");
  });

  it("accepts each valid level", () => {
    for (const level of ["off", "labels", "full"] as const) {
      const cfg = parseEmbedTenants(entry({ activityDetail: level })).get("tenant.example")!;
      expect(cfg.activityDetail).toBe(level);
    }
  });

  it("rejects an unknown level at startup rather than silently downgrading", () => {
    expect(() => parseEmbedTenants(entry({ activityDetail: "verbose" }))).toThrow(
      /activityDetail must be/
    );
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-tenants.test.ts`
Expected: FAIL — `expected undefined to be 'labels'`

- [ ] **Step 3: Add the field**

In `frontend/digichat/src/lib/embed-tenants.ts`, add to the imports at the top:

```ts
import type { ActivityDetail } from "@/lib/chat-activity";
```

Add to the `EmbedTenantConfig` type, immediately after the `lockedContact` field:

```ts
  /**
   * How much of the agent's thinking chain this tenant's visitors see.
   * "off" emits nothing, "labels" emits step labels only, "full" adds the
   * retrieved document titles. Gated server-side, so lower levels never put
   * documents on the wire. Defaults to "labels" — a tenant nobody configured
   * should not stream retrieved titles to anonymous visitors.
   */
  activityDetail: ActivityDetail;
```

Add this validation immediately after the existing `lockedContact` check (around line 168):

```ts
  if (
    v.activityDetail !== undefined &&
    v.activityDetail !== "off" &&
    v.activityDetail !== "labels" &&
    v.activityDetail !== "full"
  ) {
    throw new Error(`${ctx}: activityDetail must be "off", "labels", or "full"`);
  }
```

Add to the returned object, after the `lockedContact` line:

```ts
    activityDetail: (v.activityDetail as ActivityDetail | undefined) ?? "labels",
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-tenants.test.ts`
Expected: PASS — pre-existing tests plus the 3 new ones

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/embed-tenants.ts frontend/digichat/src/lib/embed-tenants.test.ts
git commit -m "feat(digichat): add per-tenant activityDetail config"
```

---

### Task 5: Foundry emits spans

This is the visible win: Foundry already sends search queries in `item.queries` and citation titles in the annotations, and today both are stringified into one grey label line.

**Files:**
- Modify: `frontend/digichat/src/lib/foundry-stream.ts:41-45` (event type), `:78-132` (mapping), `:134-225` (writer)
- Modify: `frontend/digichat/src/app/api/chat/route.ts:122-131`
- Test: `frontend/digichat/src/lib/foundry-stream.test.ts`

**Interfaces:**
- Consumes: `ActivitySpan`, `ACTIVITY_PART_TYPE`, `applyActivityDetail`, `ActivityDetail` from Task 1
- Produces:
  - `FoundryServerEvent` gains `{ type: "activity"; span: ActivitySpan }` and **loses** `{ type: "trace"; … }`
  - `createFoundryStreamResponse` gains a required `activityDetail: ActivityDetail` option

- [ ] **Step 1: Write the failing tests**

Append to `frontend/digichat/src/lib/foundry-stream.test.ts`:

```ts
describe("mapFoundryEvent activity spans", () => {
  it("opens the search as a started execute_tool span", () => {
    expect(mapFoundryEvent({ type: "response.file_search_call.in_progress" })).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "file_search",
        status: "started",
        label: "Searching knowledge base…",
      },
    });
  });

  it("carries the real query on the completed search span", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: { type: "file_search_call", queries: ["how does auth work"] },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "file_search",
        status: "completed",
        query: "how does auth work",
        label: 'Searched for: "how does auth work"',
      },
    });
  });

  // azure_ai_search grounding: {type:"url_citation", url, title}. See 91caa0e0.
  it("maps url_citation annotations to retrieved documents", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: {
          type: "message",
          content: [
            {
              annotations: [
                { type: "url_citation", url: "https://x/auth", title: "Auth guide" },
                { type: "url_citation", url: "https://x/keys" },
              ],
            },
          ],
        },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "retrieve",
        toolName: "file_search",
        status: "completed",
        label: "Sources",
        documents: [
          { title: "Auth guide", path: "https://x/auth" },
          { title: "https://x/keys", path: "https://x/keys" },
        ],
      },
    });
  });

  // Foundry's native file_search grounding: {filename}, no url at all.
  it("maps filename annotations to retrieved documents", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: { type: "message", content: [{ annotations: [{ filename: "auth.md" }] }] },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "retrieve",
        toolName: "file_search",
        status: "completed",
        label: "Sources",
        documents: [{ title: "auth.md", path: "auth.md" }],
      },
    });
  });

  it("emits nothing for a message with no annotations", () => {
    expect(
      mapFoundryEvent({ type: "response.output_item.done", item: { type: "message", content: [] } })
    ).toBeNull();
  });
});

describe("createFoundryStreamResponse activity detail", () => {
  const searchEvents: FoundryStreamEvent[] = [
    { type: "response.file_search_call.in_progress" },
    {
      type: "response.output_item.done",
      item: {
        type: "message",
        content: [{ annotations: [{ type: "url_citation", url: "https://x/a", title: "A" }] }],
      },
    },
    { type: "response.output_text.delta", delta: "done" },
    { type: "response.completed" },
  ];

  async function run(activityDetail: "off" | "labels" | "full"): Promise<string> {
    const { client } = fakeClient(searchEvents);
    const res = await createFoundryStreamResponse({
      projectEndpoint: "https://p",
      agentName: "agent",
      messages: [userMessage("hi")],
      conversationId: "conv_1",
      responseHeaders: {},
      activityDetail,
      openAIClientFactory: () => client,
    });
    return await drain(res);
  }

  it("streams documents at full", async () => {
    const body = await run("full");
    expect(body).toContain("data-digichatActivity");
    expect(body).toContain("https://x/a");
  });

  // The gate is server-side: a labels tenant must not receive the titles at all.
  it("withholds documents at labels", async () => {
    const body = await run("labels");
    expect(body).toContain("data-digichatActivity");
    expect(body).not.toContain("https://x/a");
  });

  it("emits no activity parts at off", async () => {
    const body = await run("off");
    expect(body).not.toContain("data-digichatActivity");
    expect(body).toContain("done");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend/digichat && npx vitest run src/lib/foundry-stream.test.ts`
Expected: FAIL — existing `mapFoundryEvent` still returns `{ type: "trace", … }`

- [ ] **Step 3: Rewrite the mapping and the writer**

In `frontend/digichat/src/lib/foundry-stream.ts`, add to the imports:

```ts
import {
  ACTIVITY_PART_TYPE,
  applyActivityDetail,
  type ActivityDetail,
  type ActivityDocument,
  type ActivitySpan,
} from "./chat-activity";
```

Replace the `FoundryServerEvent` union (lines 41–45) with:

```ts
type FoundryServerEvent =
  | { type: "text-delta"; delta: string }
  | { type: "activity"; span: ActivitySpan }
  | { type: "done" }
  | { type: "error"; message: string };
```

Replace `mapOutputItemDone` (lines 78–106) with:

```ts
function mapOutputItemDone(event: OutputItemDoneEvent): FoundryServerEvent | null {
  const item = event.item;
  if (item?.type === "file_search_call") {
    const queries = item.queries ?? [];
    const query = queries[0];
    const label = query
      ? `Searched for: ${queries.map((q) => `"${q}"`).join(", ")}`
      : FILE_SEARCH_LABEL;
    return {
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "file_search",
        status: "completed",
        ...(query ? { query } : {}),
        label,
      },
    };
  }
  if (item?.type === "message") {
    // Two citation shapes share this event: Foundry's native file_search tool
    // annotates with `filename`, while the azure_ai_search tool emits
    // `{type: "url_citation", url, title}` with no filename at all. Handle both
    // so sources show up regardless of which grounding tool an agent uses.
    const documents: ActivityDocument[] = [];
    const seen = new Set<string>();
    for (const content of item.content ?? []) {
      for (const annotation of content.annotations ?? []) {
        const path = annotation.type === "url_citation" ? annotation.url : annotation.filename;
        if (!path || seen.has(path)) continue;
        seen.add(path);
        const title =
          (annotation.type === "url_citation" ? annotation.title : annotation.filename) || path;
        documents.push({ title, path });
      }
    }
    if (documents.length > 0) {
      return {
        type: "activity",
        span: {
          operation: "retrieve",
          toolName: "file_search",
          status: "completed",
          label: "Sources",
          documents,
        },
      };
    }
  }
  return null;
}
```

Replace the `response.file_search_call.in_progress` case inside `mapFoundryEvent` (lines 121–122) with:

```ts
    case "response.file_search_call.in_progress":
      return {
        type: "activity",
        span: {
          operation: "execute_tool",
          toolName: "file_search",
          status: "started",
          label: FILE_SEARCH_LABEL,
        },
      };
```

Add `activityDetail` to the `createFoundryStreamResponse` options object (line 134–142), after `responseHeaders`:

```ts
  activityDetail: ActivityDetail;
```

Replace the `mapped.type === "trace"` branch (lines 193–203) with:

```ts
          } else if (mapped.type === "activity") {
            const span = applyActivityDetail(mapped.span, opts.activityDetail);
            if (span) {
              writer.write({
                type: ACTIVITY_PART_TYPE,
                id: `foundry-activity-${traceSeq++}`,
                data: span,
              });
            }
```

- [ ] **Step 4: Update the route caller**

In `frontend/digichat/src/app/api/chat/route.ts`, in the `foundry` branch (lines 122–131), add one option:

```ts
  if (embedConfig?.backend.type === "foundry") {
    return await createFoundryStreamResponse({
      projectEndpoint: embedConfig.backend.projectEndpoint,
      agentName: embedConfig.backend.agentName,
      messages,
      conversationId: req.headers.get("x-external-conversation"),
      responseHeaders,
      activityDetail: embedConfig.activityDetail,
      signal: req.signal,
    });
  }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/foundry-stream.test.ts src/app/api/chat/route.test.ts`
Expected: PASS — pre-existing tests plus the 8 new ones. Any pre-existing test asserting `{ type: "trace" }` from `mapFoundryEvent` must be updated to the new span shape; the two duplicate-suppression tests (`.searching` and `output_text.done` both returning `null`) must keep passing unchanged.

- [ ] **Step 6: Commit**

```bash
git add frontend/digichat/src/lib/foundry-stream.ts frontend/digichat/src/lib/foundry-stream.test.ts frontend/digichat/src/app/api/chat/route.ts
git commit -m "feat(digichat): emit rich activity spans from the Foundry provider"
```

---

### Task 6: Relay and digigraph emit spans; stop leaking upstream error bodies

**Files:**
- Modify: `frontend/digichat/src/lib/external-relay-stream.ts:149-158`
- Modify: `frontend/digichat/src/lib/stream-digigraph-trace.ts:96-109` (error leak), `:124-131` (trace write), and the `createDigigraphTraceStreamResponse` options
- Modify: `frontend/digichat/src/app/api/chat/route.ts:112-120` and `:202-210`
- Test: `frontend/digichat/src/lib/external-relay-stream.test.ts`, `frontend/digichat/src/lib/stream-digigraph-trace.test.ts` (create if absent)

**Interfaces:**
- Consumes: `ACTIVITY_PART_TYPE`, `applyActivityDetail`, `ActivityDetail` from Task 1
- Produces: `createExternalRelayStreamResponse` and `createDigigraphTraceStreamResponse` each gain a required `activityDetail: ActivityDetail` option

Neither provider can be enriched beyond `trace` without upstream changes — the relay sends only `{label, status}` and digigraph's payload is passed through opaquely. Mapping them to `operation: "chat"` spans is a faithful translation, not a downgrade.

- [ ] **Step 1: Write the failing test for the error leak**

Create `frontend/digichat/src/lib/stream-digigraph-trace.test.ts` if it does not exist, and append:

```ts
import { describe, it, expect, vi, afterEach } from "vitest";
import type { UIMessage } from "ai";
import { createDigigraphTraceStreamResponse } from "./stream-digigraph-trace";

afterEach(() => vi.restoreAllMocks());

const userMessage = (text: string) =>
  ({ id: "u1", role: "user", parts: [{ type: "text", text }] }) as UIMessage;

// A 500 body from digigraph can carry stack traces, internal hostnames, and
// prompt echoes. Streaming it verbatim to an anonymous embed visitor publishes
// all of that; the detail belongs in the server log.
it("does not stream the upstream error body to the browser", async () => {
  const secret = "Traceback: psycopg2 connect to db.internal:5432 failed";
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(secret, { status: 500, statusText: "Internal Server Error" })
  );
  const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    upstreamBearer: "tok",
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();

  expect(body).not.toContain(secret);
  expect(body).not.toContain("db.internal");
  expect(body).toMatch(/unavailable|try again/i);
  expect(errorLog).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/stream-digigraph-trace.test.ts`
Expected: FAIL — the body contains the traceback

- [ ] **Step 3: Fix the leak and switch to spans**

In `frontend/digichat/src/lib/stream-digigraph-trace.ts`, add to the imports:

```ts
import {
  ACTIVITY_PART_TYPE,
  applyActivityDetail,
  type ActivityDetail,
} from "@/lib/chat-activity";
```

Add `activityDetail: ActivityDetail;` to the `createDigigraphTraceStreamResponse` options object.

Replace the `!res.ok` block (lines 96–109) with:

```ts
      if (!res.ok) {
        // Log the upstream detail server-side; never stream it. A 500 body can
        // carry stack traces, internal hostnames, and prompt echoes, and this
        // response goes to anonymous embed visitors.
        const detail = (await res.text().catch(() => "")).trim();
        console.error(
          `[digigraph] upstream ${res.status} ${res.statusText}`,
          detail.length > 1500 ? `${detail.slice(0, 1500)}…` : detail
        );
        writer.write({
          type: "text-delta",
          id: textId,
          delta: "The assistant is unavailable right now. Please try again shortly.",
        });
        writer.write({ type: "text-end", id: textId });
        return;
      }
      if (!res.body) {
        console.error(`[digigraph] upstream ${res.status} returned an empty body`);
        writer.write({
          type: "text-delta",
          id: textId,
          delta: "The assistant is unavailable right now. Please try again shortly.",
        });
        writer.write({ type: "text-end", id: textId });
        return;
      }
```

Replace the trace write (lines 124–131) with:

```ts
        const tr = delta.digigraph_trace;
        if (tr && typeof tr === "object") {
          const payload = tr as DigigraphTracePayload;
          const label = String(payload.payload?.label ?? payload.type ?? "activity");
          const span = applyActivityDetail(
            {
              operation: "chat",
              status: payload.payload?.status === "completed" ? "completed" : "started",
              label,
            },
            opts.activityDetail
          );
          if (span) {
            writer.write({
              type: ACTIVITY_PART_TYPE,
              id: `dg-activity-${traceSeq++}`,
              data: span,
            });
          }
        }
```

- [ ] **Step 4: Switch the relay provider**

In `frontend/digichat/src/lib/external-relay-stream.ts`, add the same import block, add `activityDetail: ActivityDetail;` to the `createExternalRelayStreamResponse` options object, and replace the `event === "trace"` branch (lines 149–158) with:

```ts
          } else if (event === "trace") {
            const span = applyActivityDetail(
              {
                operation: "chat",
                status: data.status === "completed" ? "completed" : "started",
                label: String(data.label ?? "activity"),
              },
              opts.activityDetail
            );
            if (span) {
              writer.write({
                type: ACTIVITY_PART_TYPE,
                id: `relay-activity-${traceSeq++}`,
                data: span,
              });
            }
```

- [ ] **Step 5: Update the existing relay assertion**

`frontend/digichat/src/lib/external-relay-stream.test.ts:93` currently asserts the old part type. Change it to the new one and tighten it so the mapping is actually covered rather than just the part name:

```ts
    expect(out).toContain('"type":"data-digichatActivity"');
    expect(out).toContain('"operation":"chat"');
    expect(out).toContain('"label":"Searching…"');
```

Every `createExternalRelayStreamResponse` call in that file also needs `activityDetail: "full"` added to its options — the option is required, so `tsc` will point at each one.

- [ ] **Step 6: Update both route callers**

In `frontend/digichat/src/app/api/chat/route.ts`, add `activityDetail: embedConfig.activityDetail,` to the `external-relay` branch, and add this to the `createDigigraphTraceStreamResponse` call in the trace-stream branch:

```ts
      activityDetail: embedConfig?.activityDetail ?? "full",
```

The `"full"` fallback is deliberate. `embedConfig` is null on the authenticated app path, whose users are signed in — the allowlist gate exists to protect anonymous public embeds, so signed-in users see the whole chain.

- [ ] **Step 7: Run the full suite**

Run: `cd frontend/digichat && npx vitest run`
Expected: PASS — whole digichat suite green

- [ ] **Step 8: Typecheck and lint**

Run: `cd frontend/digichat && npx tsc --noEmit && npm run lint`
Expected: no errors

- [ ] **Step 9: Commit**

```bash
git add frontend/digichat/src/lib/external-relay-stream.ts frontend/digichat/src/lib/stream-digigraph-trace.ts frontend/digichat/src/lib/stream-digigraph-trace.test.ts frontend/digichat/src/lib/external-relay-stream.test.ts frontend/digichat/src/app/api/chat/route.ts
git commit -m "feat(digichat): emit activity spans from relay and digigraph; stop streaming upstream error bodies"
```

---

## Manual verification after implementation

1. Set the DataTap dev tenant to `"activityDetail": "full"` in `DIGICHAT_EMBED_TENANTS`.
2. Release digichat, mirror GHCR → ACR with `az acr import` (still manual — see the spec), point the dev revision at the new image.
3. Ask the DataTap embed a question that triggers grounding. Expect a `tool_call` row while searching, then a `tool_result` row naming the query with a titled source list — not a flat `Sources: a, b` line.
4. Flip the tenant to `"labels"`, redeploy, and confirm via the browser network panel that no document titles appear in the response body at all.
