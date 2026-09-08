import { describe, expect, it } from "vitest";
import {
  citationHits,
  chainActivities,
  distinctHitPath,
  liveActivityLabel,
  outcomeMeta,
  readableSnippet,
  stripFoundryCitationMarkers,
  toCanonRows,
  WORKING_LABEL,
  type CanonActivityRow,
} from "./activity-view";
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
  it("maps an in-flight locate tool_call to a running row with a Searching… body", () => {
    const row = onlyRow([{ kind: "tool_call", name: "digisearch", query: "auth" }]);
    expect(row).toEqual({
      kind: "tool",
      key: "tool:digisearch|auth",
      name: "Search the knowledge base",
      args: "auth",
      status: "running",
      lines: ["Searching…"],
    });
    expect(row).not.toHaveProperty("sources");
    expect(row).not.toHaveProperty("meta");
  });

  it("maps an in-flight load tool_call to Working…, not Searching…", () => {
    const row = onlyRow([{ kind: "tool_call", name: "digivault_get_note", query: "docs/auth.md" }]);
    expect(row).toMatchObject({
      kind: "tool",
      name: "Load vault note",
      status: "running",
      lines: ["Working…"],
    });
    expect(row.kind === "tool" && row.lines).not.toContain("Searching…");
  });

  it("omits args when the provider sent no query", () => {
    const row = onlyRow([{ kind: "tool_call", name: "mcp.list_tools", query: "" }]);
    expect(row).not.toHaveProperty("args");
    expect(row).toMatchObject({
      kind: "tool",
      name: "mcp.list_tools",
      status: "running",
      lines: ["Working…"],
    });
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
    });
    // Folded under the tool row — how the retrieve arrived, not a separate panel.
    expect(row).not.toHaveProperty("defaultOpen");
    expect(row.kind === "tool" && row.sources).toEqual([
      { title: "Auth", path: "docs/auth.md", tier: "peer_reviewed", year: 2024 },
      { title: "JWT", path: "docs/jwt.md", snippet: "RS256 exchange…" },
    ]);
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

  it("leaves every tool-shaped row folded by default", () => {
    const [call, trace, result] = rowsOf([
      { kind: "tool_call", name: "digisearch", query: "auth" },
      { kind: "trace", label: "Planning", done: true },
      {
        kind: "tool_result",
        name: "digisearch",
        query: "auth",
        count: 1,
        hits: [{ title: "Auth", path: "docs/auth.md" }],
      },
    ]);
    expect(call).not.toHaveProperty("defaultOpen");
    expect(trace).not.toHaveProperty("defaultOpen");
    expect(result).not.toHaveProperty("defaultOpen");
    expect(result.kind === "tool" && result.sources).toHaveLength(1);
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

  it("shows human labels, not raw tool ids", () => {
    const search = onlyRow([{ kind: "tool_call", name: "digisearch", query: "jwt" }]);
    expect(search).toMatchObject({ name: "Search the knowledge base" });
    const docs = onlyRow([
      { kind: "tool_result", name: "digivault_search_notes", query: "jwt", count: 0, hits: [] },
    ]);
    expect(docs).toMatchObject({ name: "Vault" });
    const load = onlyRow([
      { kind: "tool_result", name: "digivault_get_note", query: "1 note", count: 1, hits: [] },
    ]);
    expect(load).toMatchObject({ name: "Load vault note" });
  });

  it("does not echo the same query on the following row", () => {
    const rows = rowsOf([
      { kind: "tool_call", name: "digisearch", query: "how does RS256 token exchange work in the auth plane" },
      {
        kind: "tool_result",
        name: "digivault_get_note",
        query: "how does RS256 token exchange work in the auth plane",
        count: 1,
        hits: [],
      },
    ]);
    expect(rows[0]).toHaveProperty("args");
    expect(rows[1]).not.toHaveProperty("args");
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

describe("readableSnippet", () => {
  it("strips markdown so a heading wall becomes a sentence", () => {
    const raw = "# Auth\n\n**RS256** tokens. See [docs](https://example.invalid).";
    expect(readableSnippet(raw)).toBe("Auth RS256 tokens. See docs.");
    expect(readableSnippet(raw)).not.toContain("#");
    expect(readableSnippet(raw)).not.toContain("**");
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
    const done = keyOf({ kind: "tool_result", name: "search", query: "a", hits: [], count: 0 });
    expect(done).toBe(running);
  });
});

// The caret says what the stream said, or says nothing. It used to cycle a
// fixed script — "thinking", "routing through digigraph", … — regardless of
// what was happening, which read as a placeholder because it was one.
describe("liveActivityLabel", () => {
  it("returns nothing when the stream has named no step", () => {
    expect(liveActivityLabel([])).toBeUndefined();
    expect(liveActivityLabel([{ kind: "status", message: "hi" }])).toBeUndefined();
  });

  it("names the unfinished trace step", () => {
    expect(liveActivityLabel([{ kind: "trace", label: "Thinking", done: false }])).toBe("Thinking");
  });

  it("goes quiet once every step has finished", () => {
    expect(liveActivityLabel([{ kind: "trace", label: "Thinking", done: true }])).toBeUndefined();
  });

  it("prefers the newest unfinished step", () => {
    expect(
      liveActivityLabel([
        { kind: "trace", label: "Thinking", done: false },
        { kind: "trace", label: "Searching", done: false },
      ]),
    ).toBe("Searching");
  });

  it("names an in-flight tool by its own query", () => {
    expect(
      liveActivityLabel([{ kind: "tool_call", name: "azure_ai_search", query: "/api/config" }]),
    ).toBe('Searching for "/api/config"');
  });

  // A call's query is often still empty while it is in flight — that is the
  // whole reason the tool match is on name alone.
  it("still names a tool whose query has not arrived yet", () => {
    expect(liveActivityLabel([{ kind: "tool_call", name: "azure_ai_search", query: "" }])).toBe(
      "Searching…",
    );
  });

  it("goes quiet once the tool has returned", () => {
    expect(
      liveActivityLabel([
        { kind: "tool_call", name: "azure_ai_search", query: "auth" },
        { kind: "tool_result", name: "azure_ai_search", query: "auth", count: 1, hits: [] },
      ]),
    ).toBeUndefined();
  });
});

describe("chainActivities", () => {
  it("strips Working… so it never becomes a permanent chain row", () => {
    expect(
      chainActivities([
        { kind: "trace", label: WORKING_LABEL, done: false },
        { kind: "tool_call", name: "azure_ai_search", query: "docs" },
        { kind: "trace", label: WORKING_LABEL, done: true },
      ]),
    ).toEqual([{ kind: "tool_call", name: "azure_ai_search", query: "docs" }]);
  });

  it("keeps real traces", () => {
    expect(chainActivities([{ kind: "trace", label: "Planning", done: true }])).toEqual([
      { kind: "trace", label: "Planning", done: true },
    ]);
  });
});

describe("distinctHitPath", () => {
  it("drops the path when Foundry (and kin) set title === path", () => {
    expect(distinctHitPath("page__docs___chunk0", "page__docs___chunk0")).toBeNull();
  });

  it("keeps a real path that differs from the title", () => {
    expect(distinctHitPath("Auth overview", "docs/auth.md")).toBe("docs/auth.md");
  });
});

describe("citationHits", () => {
  it("collects unique hits from every settled search on the turn", () => {
    expect(
      citationHits([
        {
          kind: "tool_result",
          name: "azure_ai_search",
          query: "auth",
          count: 2,
          hits: [
            { title: "A", path: "a", snippet: "one" },
            { title: "B", path: "b" },
          ],
        },
        {
          kind: "tool_result",
          name: "azure_ai_search",
          query: "auth again",
          count: 1,
          hits: [{ title: "A", path: "a", snippet: "dup" }],
        },
      ]),
    ).toEqual([
      { title: "A", path: "a", snippet: "one" },
      { title: "B", path: "b" },
    ]);
  });

  it("ignores non-search activities", () => {
    expect(
      citationHits([
        { kind: "trace", label: "Planning", done: true },
        { kind: "tool_call", name: "azure_ai_search", query: "auth" },
      ]),
    ).toEqual([]);
  });

  it("prefers a hit that already carries a full body", () => {
    expect(
      citationHits([
        {
          kind: "tool_result",
          name: "digisearch",
          query: "auth",
          count: 1,
          hits: [{ title: "Auth", path: "clients/x/p001", snippet: "short" }],
        },
        {
          kind: "tool_result",
          name: "digivault_get_note",
          query: "1 note",
          count: 1,
          hits: [{ title: "Auth", path: "clients/x/p001", body: "# Auth\n\nFull note." }],
        },
      ]),
    ).toEqual([{ title: "Auth", path: "clients/x/p001", body: "# Auth\n\nFull note." }]);
  });
});

describe("stripFoundryCitationMarkers", () => {
  it("removes 【N:M†source】 glyphs from the prose", () => {
    expect(
      stripFoundryCitationMarkers(
        "Use the X-API-Key header\u30109:0\u2020source\u3011 on every request\u30109:3\u2020source\u3011.",
      ),
    ).toBe("Use the X-API-Key header on every request.");
  });
});
