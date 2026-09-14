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

import { mapFoundryEvent, type FoundryStreamEvent } from "./adapters/foundry/stream";
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

  // Superseded: reasoning items used to map unconditionally, which put a bare
  // "Thinking ✓" on every answer — including a two-word greeting that ran no
  // tools and had nothing behind the row. A step that shows nothing is chrome.
  it("drops textless reasoning rather than asserting a step it cannot show", () => {
    // The fixture carries six reasoning items, every one summary:[] content:[].
    const reasoningItems = events.filter(
      (e) =>
        e.type === "response.output_item.done" &&
        (e as { item?: { type?: string } }).item?.type === "reasoning",
    );
    expect(reasoningItems.length).toBeGreaterThan(0);
    expect(spansFromFixture().filter((s) => s.label === "Thinking")).toHaveLength(0);
  });

  it("renders reasoning the moment it carries text", () => {
    // What arrives once a reasoning summary is enabled on the agent definition.
    const withText = mapFoundryEvent({
      type: "response.output_item.done",
      item: {
        type: "reasoning",
        summary: [{ type: "summary_text", text: "Checked the OpenAPI chunks first." }],
        content: [],
      },
    } as unknown as FoundryStreamEvent);
    expect(withText).toMatchObject({
      type: "activity",
      span: { label: "Thinking", reasoningDelta: "Checked the OpenAPI chunks first." },
    });
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

  it("does not invent a second file_search row from opaque doc_N annotations", () => {
    // The fixture's message carries doc_0/doc_3 → search.windows.net citations.
    // Those have no chunk body; real hits already sit on azure_ai_search.
    expect(rows().filter((r) => r.kind === "tool_result" && r.name === "file_search")).toHaveLength(
      0,
    );
  });

  it("shows no thinking row at all while the agent emits no reasoning text", () => {
    // Six reasoning items in this stream, none with text — so none on screen.
    expect(rows().filter((r) => r.kind === "trace")).toHaveLength(0);
  });

  it("leaves a greeting with an empty chain instead of a lone Thinking row", () => {
    // "hi" runs no tools; every item it produces is a textless reasoning step.
    const greeting = [
      { type: "response.output_item.done", item: { type: "reasoning", summary: [], content: [] } },
    ] as unknown as FoundryStreamEvent[];
    const spans = greeting.map(mapFoundryEvent).filter((m) => m?.type === "activity");
    expect(spans).toHaveLength(0);
  });
});
