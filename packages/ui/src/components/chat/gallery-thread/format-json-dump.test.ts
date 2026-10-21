import { describe, expect, it } from "vitest";
import {
  MAX_REPAIR_INPUT_CHARS,
  formatJsonDump,
  formatToolDurationMs,
  humanizeToolName,
  repairPartialJson,
} from "./format-json-dump";

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

  it("pretty-prints partial streaming args, closing open brackets", () => {
    expect(formatJsonDump('{"query":"occ refund policy","limit":5,"filters":{"tag":"bil')).toBe(
      '{\n  "query": "occ refund policy",\n  "limit": 5,\n  "filters": {\n    "tag": "bil"\n  }\n}',
    );
    expect(formatJsonDump('{"query":"a","limit":')).toBe('{\n  "query": "a"\n}');
    expect(formatJsonDump('{"query":"a","lim')).toBe('{\n  "query": "a"\n}');
    expect(formatJsonDump('{"ids":[1,2,')).toBe('{\n  "ids": [\n    1,\n    2\n  ]\n}');
    expect(formatJsonDump('{"ok":tr')).toBe("{}");
    expect(formatJsonDump("{")).toBe("{}");
  });

  it("leaves non-JSON strings alone", () => {
    expect(formatJsonDump("not json")).toBe("not json");
  });
});

/**
 * DIG-4818: CodeQL js/polynomial-redos alert 196 on the whitespace strip in
 * repairPartialJson. A whitespace run inside the text made the old
 * out.replace(/\s+$/, "") re-try the anchor at every position of the run, so
 * the repair cost quadratic time and froze the render thread.
 */
describe("formatJsonDump on a long whitespace payload (DIG-4818)", () => {
  it("repairs a 50000-space run inside the text in linear time", () => {
    const payload = `{"a":${" ".repeat(50000)}tru}`;
    const started = performance.now();
    const out = formatJsonDump(payload);
    const elapsed = performance.now() - started;
    // The old regex needed ~875 ms for this payload on this machine.
    expect(elapsed).toBeLessThan(500);
    // Nothing is cut: the text does not parse, so it is shown raw.
    expect(out).toBe(payload);
  });

  it("repairs a payload that is exactly at the cap", () => {
    const head = `{"a":1,`;
    const tail = `"b":`;
    const payload = head + " ".repeat(MAX_REPAIR_INPUT_CHARS - head.length - tail.length) + tail;
    expect(payload.length).toBe(MAX_REPAIR_INPUT_CHARS);
    expect(formatJsonDump(payload)).toBe('{\n  "a": 1\n}');
  });

  it("does not repair past the cap and never cuts the text", () => {
    const head = `{"a":1,`;
    const tail = `"b":`;
    const payload = head + " ".repeat(MAX_REPAIR_INPUT_CHARS) + tail;
    expect(payload.length).toBeGreaterThan(MAX_REPAIR_INPUT_CHARS);
    const started = performance.now();
    const out = formatJsonDump(payload);
    const elapsed = performance.now() - started;
    expect(elapsed).toBeLessThan(500);
    expect(out).toBe(payload);
    expect(repairPartialJson(payload)).toBeUndefined();
  });
});

describe("formatToolDurationMs", () => {
  it("shows milliseconds under 100ms, then seconds with one decimal", () => {
    expect(formatToolDurationMs(0)).toBe("0ms");
    expect(formatToolDurationMs(42)).toBe("42ms");
    expect(formatToolDurationMs(412)).toBe("0.4s");
    expect(formatToolDurationMs(999)).toBe("1.0s");
  });

  it("switches from milliseconds to seconds at one second", () => {
    expect(formatToolDurationMs(1000)).toBe("1.0s");
    expect(formatToolDurationMs(2300)).toBe("2.3s");
    expect(formatToolDurationMs(65000)).toBe("1m 5s");
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
