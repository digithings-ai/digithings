import { describe, expect, it } from "vitest";
import { outcomeMeta, toCanonRows, type CanonActivityRow } from "./activity-view";
import type { DigiChatActivity } from "./types";

function rowsOf(activities: DigiChatActivity[]): CanonActivityRow[] {
  return toCanonRows(activities);
}

function onlyRow(activities: DigiChatActivity[]): CanonActivityRow {
  const rows = rowsOf(activities);
  expect(rows).toHaveLength(1);
  return rows[0];
}

describe("toCanonRows — tool calls", () => {
  it("maps an in-flight tool_call to a running ChatToolCall row with no body", () => {
    const row = onlyRow([{ kind: "tool_call", name: "digivault.search", query: "auth" }]);
    expect(row).toEqual({
      kind: "tool",
      key: "tool:digivault.search|auth",
      name: "digivault.search",
      args: "auth",
      status: "running",
    });
    // No sources and no meta => ChatToolCall renders a plain, non-expandable row.
    expect(row).not.toHaveProperty("sources");
    expect(row).not.toHaveProperty("meta");
  });

  it("omits args when the provider sent no query", () => {
    const row = onlyRow([{ kind: "tool_call", name: "mcp.list_tools", query: "" }]);
    expect(row).not.toHaveProperty("args");
    expect(row).toMatchObject({ kind: "tool", name: "mcp.list_tools", status: "running" });
  });

  it("maps a tool_result to a settled row carrying its sources", () => {
    const row = onlyRow([
      {
        kind: "tool_result",
        name: "digivault.search",
        query: "how does auth work",
        count: 2,
        hits: [
          { title: "Auth", path: "docs/auth.md", tier: "peer_reviewed", year: 2024 },
          { title: "JWT", path: "docs/jwt.md", snippet: "RS256 exchange…" },
        ],
      },
    ]);
    expect(row).toMatchObject({
      kind: "tool",
      name: "digivault.search",
      args: "how does auth work",
      status: "ok",
      meta: "2 notes",
      // ChatToolCall renders no body while folded, so citations must start
      // open or they are absent from the server markup entirely.
      defaultOpen: true,
    });
    expect(row.kind === "tool" && row.sources).toHaveLength(2);
  });

  it("gives a zero-hit result an honest head and no fold-out body", () => {
    const row = onlyRow([
      { kind: "tool_result", name: "digivault.search", query: "nothing", count: 0, hits: [] },
    ]);
    expect(row).toMatchObject({ kind: "tool", status: "ok", meta: "no hits" });
    // An expandable block that folds open onto nothing is worse than a plain row.
    expect(row).not.toHaveProperty("sources");
    expect(row).not.toHaveProperty("defaultOpen");
  });

  it("leaves the noisy rows folded — only citations open by default", () => {
    const [call, trace] = rowsOf([
      { kind: "tool_call", name: "digivault.search", query: "auth" },
      { kind: "trace", label: "Planning", done: true },
    ]);
    expect(call).not.toHaveProperty("defaultOpen");
    expect(trace).not.toHaveProperty("defaultOpen");
  });

  it("maps a trace step to a bodyless tool row, running until done", () => {
    const rows = rowsOf([
      { kind: "trace", label: "Searching the vault", done: false },
      { kind: "trace", label: "Drafting the answer", done: true },
    ]);
    expect(rows[0]).toMatchObject({ kind: "tool", name: "Searching the vault", status: "running" });
    expect(rows[1]).toMatchObject({ kind: "tool", name: "Drafting the answer", status: "ok" });
    expect(rows[0]).not.toHaveProperty("sources");
  });
});

describe("toCanonRows — reasoning, briefs and asides", () => {
  it("maps reasoning to a ChatThinking disclosure carrying the whole blob", () => {
    const text = "First I check the vault.\nThen I compare the two answers.";
    const row = onlyRow([{ kind: "reasoning", text }]);
    expect(row).toEqual({ kind: "thinking", key: "reasoning", label: "reasoning", text });
  });

  it("maps a brief to a card row, dropping an empty questions list", () => {
    const withQuestions = onlyRow([
      {
        kind: "brief",
        themes: [{ label: "Auth", summary: "RS256 tokens" }],
        questions: ["Which tenant?"],
      },
    ]);
    expect(withQuestions).toMatchObject({ kind: "brief", questions: ["Which tenant?"] });

    const bare = onlyRow([{ kind: "brief", themes: [{ label: "Auth", summary: "RS256" }] }]);
    expect(bare).not.toHaveProperty("questions");
  });

  it("maps a status message to a canon system aside", () => {
    const row = onlyRow([{ kind: "status", message: 'Found results for "auth".' }]);
    expect(row).toEqual({ kind: "aside", key: "status-0", message: 'Found results for "auth".' });
  });
});

describe("toCanonRows — ordering and identity", () => {
  it("preserves order across a full mixed chain", () => {
    const rows = rowsOf([
      { kind: "trace", label: "Planning", done: true },
      { kind: "tool_call", name: "digivault.search", query: "auth" },
      {
        kind: "tool_result",
        name: "digivault.search",
        query: "auth",
        count: 1,
        hits: [{ title: "Auth", path: "docs/auth.md" }],
      },
      { kind: "status", message: "Search completed." },
      { kind: "reasoning", text: "weighing the two docs" },
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["tool", "tool", "tool", "aside", "thinking"]);
  });

  it("keys by position, so repeated identical rows stay distinct", () => {
    const rows = rowsOf([
      { kind: "trace", label: "Thinking", done: false },
      { kind: "trace", label: "Thinking", done: false },
    ]);
    expect(new Set(rows.map((r) => r.key)).size).toBe(2);
  });

  it("returns nothing for an empty chain", () => {
    expect(toCanonRows([])).toEqual([]);
  });
});

describe("outcomeMeta", () => {
  it("singularizes one note and reports emptiness honestly", () => {
    expect(outcomeMeta(1)).toBe("1 note");
    expect(outcomeMeta(3)).toBe("3 notes");
    expect(outcomeMeta(0)).toBe("no hits");
  });
});

// Regression: rows were keyed `${kind}-${index}`, but toDigiChatActivity appends
// reasoning LAST, so its index climbs with every tool row that arrives. Since
// ChatThinking is uncontrolled, the changed key unmounted it — a disclosure the
// reader had opened collapsed under their cursor mid-stream, text and all.
describe("row keys survive the stream", () => {
  it("keeps the reasoning key fixed as tool rows arrive", () => {
    const keyOf = (acts: DigiChatActivity[]) =>
      toCanonRows(acts).find((r) => r.kind === "thinking")?.key;

    const reasoning: DigiChatActivity = { kind: "reasoning", text: "thinking..." };
    const one = keyOf([reasoning]);
    const two = keyOf([{ kind: "tool_call", name: "search", query: "a" }, reasoning]);
    const three = keyOf([
      { kind: "tool_call", name: "search", query: "a" },
      { kind: "tool_call", name: "fetch", query: "b" },
      reasoning,
    ]);

    expect(one).toBeDefined();
    expect(two).toBe(one);
    expect(three).toBe(one);
  });

  it("keeps a tool row's key stable when it settles from call to result", () => {
    const keyOf = (a: DigiChatActivity) => toCanonRows([a])[0]?.key;
    const running = keyOf({ kind: "tool_call", name: "search", query: "a" });
    const done = keyOf({ kind: "tool_result", name: "search", query: "a", hits: [] } as DigiChatActivity);
    expect(done).toBe(running);
  });
});
