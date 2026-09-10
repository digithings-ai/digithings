import { describe, expect, it } from "vitest";
import { searchMethodFromArgs, toolRowTitle } from "./tool-display";

describe("searchMethodFromArgs", () => {
  it("defaults to semantic when the model omitted mode", () => {
    expect(searchMethodFromArgs(undefined)).toBe("semantic");
    expect(searchMethodFromArgs({ query: "jwt" })).toBe("semantic");
    expect(searchMethodFromArgs({ mode: "vector" })).toBe("semantic");
  });

  it("maps keyword and hybrid from tool args", () => {
    expect(searchMethodFromArgs({ mode: "keyword" })).toBe("keyword");
    expect(searchMethodFromArgs({ search_mode: "hybrid" })).toBe("hybrid");
  });
});

describe("toolRowTitle", () => {
  it("keeps the exact backend tool id, including underscores", () => {
    expect(toolRowTitle("digisearch")).toBe("digisearch");
    expect(toolRowTitle("digisearch", { mode: "keyword" })).toBe("digisearch");
    expect(toolRowTitle("digivault_get_note")).toBe("digivault_get_note");
    expect(toolRowTitle("digivault_search_notes")).toBe("digivault_search_notes");
    expect(toolRowTitle("web_search")).toBe("web_search");
  });
});
