import { describe, expect, it } from "vitest";
import { formatJsonDump, formatToolDurationMs, humanizeToolName } from "./format-json-dump";

describe("formatJsonDump", () => {
  it("pretty-prints compact JSON strings", () => {
    expect(formatJsonDump('{"query":"run digigraph docker command"}')).toBe(
      '{\n  "query": "run digigraph docker command"\n}',
    );
  });

  it("pretty-prints objects", () => {
    expect(formatJsonDump({ vault_path: "clients/digithings/p001" })).toBe(
      '{\n  "vault_path": "clients/digithings/p001"\n}',
    );
  });

  it("leaves non-JSON strings alone", () => {
    expect(formatJsonDump("not json")).toBe("not json");
  });
});

describe("formatToolDurationMs", () => {
  it("shows milliseconds under one second instead of <1s", () => {
    expect(formatToolDurationMs(0)).toBe("0ms");
    expect(formatToolDurationMs(412)).toBe("412ms");
    expect(formatToolDurationMs(999)).toBe("999ms");
  });

  it("shows seconds at 1s and above", () => {
    expect(formatToolDurationMs(1000)).toBe("1.0s");
    expect(formatToolDurationMs(2300)).toBe("2.3s");
  });
});

describe("humanizeToolName", () => {
  it("keeps the exact backend tool id, including underscores", () => {
    expect(humanizeToolName("digisearch")).toBe("digisearch");
    expect(humanizeToolName("digisearch", '{"mode":"keyword"}')).toBe("digisearch");
    expect(humanizeToolName("digisearch", '{"search_mode":"hybrid"}')).toBe("digisearch");
    expect(humanizeToolName("digisearch", '{"search_type":"keyword"}')).toBe("digisearch");
  });

  it("keeps fetch_all and research ids verbatim regardless of method args", () => {
    expect(humanizeToolName("digisearch_fetch_all")).toBe("digisearch_fetch_all");
    expect(humanizeToolName("digisearch_research", '{"mode":"hybrid"}')).toBe(
      "digisearch_research",
    );
  });

  it("keeps vault and web tool ids verbatim", () => {
    expect(humanizeToolName("digivault_search_notes")).toBe("digivault_search_notes");
    expect(humanizeToolName("digivault_get_note")).toBe("digivault_get_note");
    expect(humanizeToolName("web_search")).toBe("web_search");
  });
});
