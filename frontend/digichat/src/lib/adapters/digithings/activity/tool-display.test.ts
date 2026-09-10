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
  it("names digisearch by retrieval method", () => {
    expect(toolRowTitle("digisearch")).toBe("digisearch semantic");
    expect(toolRowTitle("digisearch", { mode: "keyword" })).toBe("digisearch keyword");
    expect(toolRowTitle("digisearch", { mode: "hybrid" })).toBe("digisearch hybrid");
  });

  it("humanizes vault tools like get-note vs search", () => {
    expect(toolRowTitle("digivault_get_note")).toBe("digivault get note");
    expect(toolRowTitle("digivault_search_notes")).toBe("digivault search notes");
  });

  it("suffixes fetch_all and research with the retrieval method", () => {
    expect(toolRowTitle("digisearch_fetch_all")).toBe("digisearch fetch all (semantic)");
    expect(toolRowTitle("digisearch_fetch_all", { search_type: "keyword" })).toBe(
      "digisearch fetch all (keyword)",
    );
    expect(toolRowTitle("digisearch_research", { mode: "hybrid" })).toBe(
      "digisearch research (hybrid)",
    );
  });
});
