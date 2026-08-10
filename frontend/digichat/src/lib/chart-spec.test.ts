import { describe, expect, it } from "vitest";
import { parseChartEnvelope } from "./chart-spec";

describe("parseChartEnvelope", () => {
  it("returns the spec for a valid chart envelope", () => {
    const raw = JSON.stringify({
      type: "chart",
      spec: {
        xAxis: { type: "category", data: ["A", "B", "C"] },
        yAxis: { type: "value" },
        series: [{ type: "bar", data: [1, 2, 3] }],
      },
    });
    const spec = parseChartEnvelope(raw);
    expect(spec).not.toBeNull();
    expect(spec?.series).toEqual([{ type: "bar", data: [1, 2, 3] }]);
  });

  it("tolerates leading/trailing whitespace", () => {
    const raw = `\n   ${JSON.stringify({ type: "chart", spec: { series: [] } })}\n`;
    expect(parseChartEnvelope(raw)).toEqual({ series: [] });
  });

  it("returns null for invalid JSON", () => {
    expect(parseChartEnvelope("{ not json")).toBeNull();
  });

  it("returns null when type is not 'chart'", () => {
    expect(parseChartEnvelope(JSON.stringify({ type: "table", spec: {} }))).toBeNull();
  });

  it("returns null when spec is missing", () => {
    expect(parseChartEnvelope(JSON.stringify({ type: "chart" }))).toBeNull();
  });

  it("returns null when spec is not an object", () => {
    expect(parseChartEnvelope(JSON.stringify({ type: "chart", spec: [1, 2] }))).toBeNull();
    expect(parseChartEnvelope(JSON.stringify({ type: "chart", spec: "oops" }))).toBeNull();
  });

  it("returns null for non-JSON content like markdown prose", () => {
    expect(parseChartEnvelope("Just some text")).toBeNull();
    expect(parseChartEnvelope("")).toBeNull();
  });
});
