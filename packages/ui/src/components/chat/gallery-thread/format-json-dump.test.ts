import { describe, expect, it } from "vitest";
import {
  MAX_REPAIR_INPUT_CHARS,
  formatJsonDump,
  formatToolDurationMs,
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
  // The pre-fix code needed ~0.8-1.05 s for the 50000-space payload and
  // ~1.4-1.9 s for the at-cap payload on this M5 Pro. A 500 ms bound sat
  // only ~2-4x below that cost, so a machine ~2x faster would have let the
  // bug through green; 100 ms is ~200x above the fixed cost (~0.2-0.5 ms
  // measured) and ~8-19x below the old one. The issue asks for "under
  // 500 ms"; this is stricter.
  const TIME_BUDGET_MS = 100;

  /** Fastest of three runs: a scheduler stall or a GC pause can only add time. */
  function fastest(run: () => void): number {
    let best = Number.POSITIVE_INFINITY;
    for (let i = 0; i < 3; i++) {
      const started = performance.now();
      run();
      best = Math.min(best, performance.now() - started);
    }
    return best;
  }

  it("runs the repair over a 50000-space run inside the text in linear time", () => {
    const payload = `{"a":${" ".repeat(50000)}tru}`;
    let out = "";
    const elapsed = fastest(() => {
      out = formatJsonDump(payload);
    });
    expect(elapsed).toBeLessThan(TIME_BUDGET_MS);
    // Nothing is cut: the text does not parse, so it is shown raw.
    expect(out).toBe(payload);
    // The payload is under the cap, so the repair path really ran.
    expect(repairPartialJson(payload)).toBeDefined();
  }, 30_000);

  it("repairs a payload that is exactly at the cap", () => {
    const head = `{"a":1,`;
    const tail = `"b":`;
    const payload = head + " ".repeat(MAX_REPAIR_INPUT_CHARS - head.length - tail.length) + tail;
    expect(payload.length).toBe(MAX_REPAIR_INPUT_CHARS);
    // The cap is part of the fix, so its value is pinned: a silently lowered
    // cap would render large tool args raw with no test noticing.
    expect(MAX_REPAIR_INPUT_CHARS).toBe(64 * 1024);
    let out = "";
    const elapsed = fastest(() => {
      out = formatJsonDump(payload);
    });
    expect(elapsed).toBeLessThan(TIME_BUDGET_MS);
    expect(out).toBe('{\n  "a": 1\n}');
  }, 30_000);

  it("does not repair past the cap and never cuts the text", () => {
    const head = `{"a":1,`;
    const tail = `"b":`;
    const payload = head + " ".repeat(MAX_REPAIR_INPUT_CHARS) + tail;
    expect(payload.length).toBeGreaterThan(MAX_REPAIR_INPUT_CHARS);
    // Content before timing: the cap is a deterministic guard and must not be
    // masked by a machine-speed assertion.
    expect(formatJsonDump(payload)).toBe(payload);
    expect(repairPartialJson(payload)).toBeUndefined();
    const elapsed = fastest(() => {
      formatJsonDump(payload);
    });
    expect(elapsed).toBeLessThan(TIME_BUDGET_MS);
  }, 30_000);

  it("still pretty-prints valid JSON larger than the cap", () => {
    // The cap guards the repair path only. Valid JSON never reaches the
    // repair, so a big tool result is still formatted instead of shown raw.
    const big = JSON.stringify({ blob: "x".repeat(MAX_REPAIR_INPUT_CHARS * 2) });
    expect(big.length).toBeGreaterThan(MAX_REPAIR_INPUT_CHARS);
    expect(formatJsonDump(big)).toBe(JSON.stringify(JSON.parse(big), null, 2));
  }, 30_000);
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
