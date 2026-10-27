import { describe, expect, it, vi } from "vitest";
import { spanMetrics, writeSpanMetric } from "./analytics";
import { fakeAnalytics } from "../test/fakes";
import type { SpanRecord } from "./types";

function record(
  overrides: Partial<SpanRecord["span"]> = {},
  resourceAttributes: SpanRecord["resource"]["attributes"] = [],
): SpanRecord {
  return {
    resource: { attributes: resourceAttributes },
    scope: { name: "s" },
    span: {
      traceId: "0af7651916cd43dd8448eb211c80319c",
      spanId: "b7ad6b7169203331",
      name: "chat",
      startTimeUnixNano: "1700000000000000000",
      endTimeUnixNano: "1700000000250000000",
      attributes: [],
      ...overrides,
    },
  };
}

describe("spanMetrics", () => {
  it("reads the model, the tokens and the latency off the span", () => {
    const metrics = spanMetrics(
      record(
        {
          kind: 3,
          status: { code: 1 },
          attributes: [
            { key: "gen_ai.response.model", value: { stringValue: "gpt-4o-mini" } },
            { key: "gen_ai.usage.input_tokens", value: { intValue: "10" } },
            { key: "gen_ai.usage.output_tokens", value: { intValue: "20" } },
            { key: "digitrace.cost_usd", value: { doubleValue: 0.002 } },
          ],
        },
        [{ key: "service.name", value: { stringValue: "digichat" } }],
      ),
      "digithings",
      "digitrace-digichat",
    );

    expect(metrics).toEqual({
      tenant: "digithings",
      source: "digitrace-digichat",
      serviceName: "digichat",
      model: "gpt-4o-mini",
      status: "STATUS_CODE_OK",
      kind: "SPAN_KIND_CLIENT",
      inputTokens: 10,
      outputTokens: 20,
      durationMs: 250,
      costUsd: 0.002,
    });
  });

  it("falls back to zero and 'unknown' rather than inventing values", () => {
    const metrics = spanMetrics(record(), "digithings", "digitrace-digichat");
    expect(metrics).toMatchObject({
      serviceName: "unknown",
      model: "unknown",
      status: "STATUS_CODE_UNSET",
      kind: "SPAN_KIND_UNSPECIFIED",
      inputTokens: 0,
      outputTokens: 0,
      costUsd: 0,
      durationMs: 250,
    });
  });

  it("lets the span's own attributes win over the resource's", () => {
    const metrics = spanMetrics(
      record(
        { attributes: [{ key: "gen_ai.request.model", value: { stringValue: "span-model" } }] },
        [{ key: "gen_ai.request.model", value: { stringValue: "resource-model" } }],
      ),
      "digithings",
      "digitrace-digichat",
    );
    expect(metrics.model).toBe("span-model");
  });
});

describe("writeSpanMetric", () => {
  const metrics = {
    tenant: "digithings",
    source: "digitrace-digichat",
    serviceName: "digichat",
    model: "gpt-4o-mini",
    status: "STATUS_CODE_OK",
    kind: "SPAN_KIND_CLIENT",
    inputTokens: 10,
    outputTokens: 20,
    durationMs: 250,
    costUsd: 0.002,
  };

  it("writes one point, indexed by tenant", () => {
    const analytics = fakeAnalytics();
    writeSpanMetric(analytics.dataset, metrics);
    expect(analytics.points).toEqual([
      {
        indexes: ["digithings"],
        blobs: [
          "digithings",
          "digitrace-digichat",
          "digichat",
          "gpt-4o-mini",
          "STATUS_CODE_OK",
          "SPAN_KIND_CLIENT",
        ],
        doubles: [10, 20, 250, 0.002, 1],
      },
    ]);
  });

  it("does nothing when the binding is absent", () => {
    expect(() => writeSpanMetric(undefined, metrics)).not.toThrow();
  });

  it("swallows a write failure: the aggregates are an estimate, the archive is the record", () => {
    const dataset = {
      writeDataPoint: vi.fn(() => {
        throw new Error("AE unavailable");
      }),
    } as unknown as AnalyticsEngineDataset;
    expect(() => writeSpanMetric(dataset, metrics)).not.toThrow();
  });
});
