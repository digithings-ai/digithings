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
    expect(toolRowTitle("digisearch", { mode: "hybrid" })).toBe("digisearch");
  });

  it("keeps vault and web tool ids verbatim", () => {
    expect(toolRowTitle("digivault_get_note")).toBe("digivault_get_note");
    expect(toolRowTitle("digivault_search_notes")).toBe("digivault_search_notes");
    expect(toolRowTitle("web_search")).toBe("web_search");
  });

  it("keeps fetch_all and research ids verbatim regardless of method args", () => {
    expect(toolRowTitle("digisearch_fetch_all")).toBe("digisearch_fetch_all");
    expect(toolRowTitle("digisearch_fetch_all", { search_type: "keyword" })).toBe(
      "digisearch_fetch_all",
    );
    expect(toolRowTitle("digisearch_research", { mode: "hybrid" })).toBe("digisearch_research");
  });
});
