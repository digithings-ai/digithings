/**
 * The Foundry adapter, run against events RECORDED off the live DataTap agent
 * rather than against events we imagined it sends.
 *
 * This exists because the guessed version was wrong in every particular. The
 * adapter was written for `file_search_call` and `response.file_search_call.*`;
 * the agent is wired to the `azure_ai_search` tool and emits none of those. So
 * a docs question produced 6 reasoning steps, a search with its query, and the
 * retrieved chunks — and the transcript showed a single bare trace line,
 * because every one of those items fell through the switch's `default`.
 *
 * The fixture is one real `response.output_item.*` stream (a docs question),
 * trimmed of text deltas and truncated chunk bodies. Re-record with the tap in
 * the session scratchpad if the agent's tool wiring changes.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { mapFoundryEvent, type FoundryStreamEvent } from "./foundry-stream";
import { toDigiChatActivity, sanitizeActivitySpan, type ActivitySpan } from "./chat-activity";

const events: FoundryStreamEvent[] = JSON.parse(
  readFileSync(join(__dirname, "__fixtures__/foundry-docs-question.events.json"), "utf8"),
);

/** The spans the adapter produces from the real stream, in order. */
function spansFromFixture(): ActivitySpan[] {
  const spans: ActivitySpan[] = [];
  for (const event of events) {
    const mapped = mapFoundryEvent(event);
    if (mapped?.type === "activity") {
      const clean = sanitizeActivitySpan(mapped.span);
      if (clean) spans.push(clean);
    }
  }
  return spans;
}

describe("the recorded stream", () => {
  it("is the shape we recorded — four item types, no file_search anywhere", () => {
    const itemTypes = new Set(
      events
        .map((e) => (e as { item?: { type?: string } }).item?.type)
        .filter((t): t is string => Boolean(t)),
    );
    expect([...itemTypes].sort()).toEqual([
      "azure_ai_search_call",
      "azure_ai_search_call_output",
      "message",
      "reasoning",
    ]);
    // The branch the adapter was originally written against never fires here.
    expect(itemTypes.has("file_search_call")).toBe(false);
    expect(events.some((e) => String(e.type).includes("file_search_call"))).toBe(false);
  });
});

describe("mapFoundryEvent over the recorded stream", () => {
  it("no longer drops the whole chain on the floor", () => {
    // Before: only the `message` annotations mapped — one span out of nine items.
    expect(spansFromFixture().length).toBeGreaterThan(1);
  });

  it("surfaces the search with the model's own query as the tool input", () => {
    const search = spansFromFixture().find(
      (s) => s.operation === "execute_tool" && s.status === "completed",
    );
    expect(search).toMatchObject({ toolName: "azure_ai_search", status: "completed" });
    expect(search?.query).toBe("/api/config endpoint return DataTapStream");
    expect(search?.label).toContain("/api/config endpoint return DataTapStream");
  });

  it("opens the search row while it is still running, before the query is known", () => {
    // `.added` carries `arguments: ""`, so the started span names the tool only.
    const started = spansFromFixture().find(
      (s) => s.operation === "execute_tool" && s.status === "started",
    );
    expect(started).toMatchObject({ toolName: "azure_ai_search", status: "started" });
    expect(started?.query).toBeUndefined();
  });

  it("carries the retrieved chunks, not just the doc_N citations", () => {
    const retrieve = spansFromFixture().find((s) => s.operation === "retrieve" && s.documents);
    expect(retrieve?.documents?.length).toBeGreaterThan(0);
    // Real chunk ids beat the `message` annotations, which title every source
    // `doc_0`/`doc_3` and point each url at the search service root.
    expect(retrieve?.documents?.[0].title).not.toMatch(/^doc_\d+$/);
    expect(retrieve?.documents?.[0].snippet).toBeTruthy();
  });

  it("reports that reasoning happened without inventing what was reasoned", () => {
    const reasoning = spansFromFixture().filter((s) => s.label === "Thinking");
    expect(reasoning.length).toBeGreaterThan(0);
    // The agent returns summary:[] content:[] and refuses a per-call
    // reasoning summary alongside agent_reference, so there is no text to show.
    for (const span of reasoning) expect(span.reasoningDelta).toBeUndefined();
  });
});

describe("the rows a reader ends up seeing", () => {
  const rows = () => toDigiChatActivity(spansFromFixture());

  it("collapses started+completed into ONE search row, not two", () => {
    const searches = rows().filter(
      (r) => (r.kind === "tool_call" || r.kind === "tool_result") && r.name === "azure_ai_search",
    );
    expect(searches).toHaveLength(1);
  });

  it("settles that row with the query and its sources", () => {
    const row = rows().find((r) => r.kind === "tool_result");
    expect(row).toBeDefined();
    if (row?.kind === "tool_result") {
      expect(row.query).toBe("/api/config endpoint return DataTapStream");
      expect(row.hits.length).toBeGreaterThan(0);
    }
  });

  it("shows the thinking step once, not once per reasoning item", () => {
    // The stream carried six reasoning items for this one answer.
    const thinking = rows().filter((r) => r.kind === "trace" && r.label === "Thinking");
    expect(thinking).toHaveLength(1);
  });
});
