import { describe, expect, it } from "vitest";
import {
  HOUSE_BUILTIN_TOOL_IDS,
  countToolSurface,
  expandToolRows,
} from "./tool-surface";

describe("expandToolRows", () => {
  it("keeps the tools a row declares and does not substitute", () => {
    const rows = expandToolRows([
      {
        id: "tickets",
        tools: [{ id: "tickets_search" }, { id: "tickets_get" }],
      },
    ]);
    expect(rows).toEqual([
      {
        id: "tickets",
        tools: ["tickets_search", "tickets_get"],
        builtin: false,
      },
    ]);
  });

  it("gives a house row that names no tools its built-in pair", () => {
    const rows = expandToolRows([{ id: "digisearch" }, { id: "digivault" }]);
    expect(rows[0]?.tools).toEqual(HOUSE_BUILTIN_TOOL_IDS.digisearch);
    expect(rows[0]?.builtin).toBe(true);
    expect(rows[1]?.tools).toEqual(HOUSE_BUILTIN_TOOL_IDS.digivault);
    expect(rows[1]?.builtin).toBe(true);
  });

  it("gives an unbroken-down server outside the house set nothing", () => {
    expect(expandToolRows([{ id: "warehouse" }])).toEqual([
      { id: "warehouse", tools: [], builtin: false },
    ]);
  });

  it("prefers declared tools over the built-in pair", () => {
    const rows = expandToolRows([
      { id: "digisearch", tools: [{ id: "digisearch_semantic" }] },
    ]);
    expect(rows[0]?.tools).toEqual(["digisearch_semantic"]);
    expect(rows[0]?.builtin).toBe(false);
  });
});

describe("countToolSurface", () => {
  const allOn = { isOn: () => true, isToolOn: () => true };

  it("counts a server once and each tool once", () => {
    const counts = countToolSurface(
      [
        {
          id: "tickets",
          tools: [
            { id: "tickets_search" },
            { id: "tickets_list" },
            { id: "tickets_get" },
          ],
        },
        { id: "digisearch" },
      ],
      allOn,
    );
    // 3 ticket tools + the digisearch built-in pair, on 2 servers.
    expect(counts).toEqual({ servers: 2, tools: 5 });
  });

  it("drops a row that is off, including its tools", () => {
    const counts = countToolSurface(
      [
        { id: "tickets", tools: [{ id: "tickets_get" }] },
        { id: "digivault" },
      ],
      { isOn: (id) => id !== "tickets", isToolOn: () => true },
    );
    expect(counts).toEqual({
      servers: 1,
      tools: (HOUSE_BUILTIN_TOOL_IDS.digivault ?? []).length,
    });
  });

  it("drops a single tool that is off but keeps the row", () => {
    const counts = countToolSurface(
      [
        {
          id: "tickets",
          tools: [{ id: "tickets_get" }, { id: "tickets_list" }],
        },
      ],
      { isOn: () => true, isToolOn: (id) => id !== "tickets_get" },
    );
    expect(counts).toEqual({ servers: 1, tools: 1 });
  });

  it("counts an on server nobody broke down as one tool", () => {
    expect(countToolSurface([{ id: "warehouse" }], allOn)).toEqual({
      servers: 1,
      tools: 1,
    });
  });
});
