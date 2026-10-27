import { describe, expect, it } from "vitest";
import {
  attributesToObject,
  durationMs,
  INDEX_ATTRIBUTE_ALLOWLIST,
  indexableAttributes,
  kindName,
  pick,
  pickNumber,
  statusName,
} from "./attributes";
import type { OtlpSpan } from "./types";

describe("attributesToObject", () => {
  it("flattens scalars and first key wins", () => {
    expect(
      attributesToObject([
        { key: "a", value: { stringValue: "first" } },
        { key: "a", value: { stringValue: "second" } },
        { key: "b", value: { intValue: "7" } },
        { key: "c", value: { boolValue: true } },
        { key: "d", value: {} },
        { key: "", value: { stringValue: "no key" } },
      ]),
    ).toEqual({ a: "first", b: "7", c: "true" });
  });
});

describe("indexableAttributes", () => {
  it("keeps the allowlisted keys", () => {
    expect(
      indexableAttributes([
        { key: "gen_ai.request.model", value: { stringValue: "gpt-4o-mini" } },
        { key: "service.name", value: { stringValue: "digichat" } },
        { key: "digi.input.sha256", value: { stringValue: "a".repeat(64) } },
      ]),
    ).toEqual({
      "gen_ai.request.model": "gpt-4o-mini",
      "service.name": "digichat",
      "digi.input.sha256": "a".repeat(64),
    });
  });

  it("drops a content preview, because a preview is content", () => {
    const kept = indexableAttributes([
      { key: "digi.input.preview", value: { stringValue: "the model will say" } },
      { key: "digi.output.preview", value: { stringValue: "here is the answer" } },
    ]);
    expect(kept).toEqual({});
    expect(INDEX_ATTRIBUTE_ALLOWLIST.has("digi.input.preview")).toBe(false);
    expect(INDEX_ATTRIBUTE_ALLOWLIST.has("digi.output.preview")).toBe(false);
  });

  it("drops a key the allowlist does not name", () => {
    expect(indexableAttributes([{ key: "arbitrary.kwarg", value: { stringValue: "x" } }])).toEqual(
      {},
    );
  });

  it("drops a non-scalar value, which the jsonb column would store as an object", () => {
    expect(
      indexableAttributes([
        {
          key: "gen_ai.request.model",
          value: { arrayValue: { values: [{ stringValue: "a" }] } },
        },
      ]),
    ).toEqual({});
  });
});

describe("pick and pickNumber", () => {
  it("takes the first present key in order", () => {
    expect(pick({ b: "second" }, ["a", "b"])).toBe("second");
    expect(pick({}, ["a"])).toBeUndefined();
    expect(pick({ a: "" }, ["a"])).toBeUndefined();
  });

  it("takes the first finite number", () => {
    expect(pickNumber({ a: "nope", b: "12" }, ["a", "b"])).toBe(12);
    expect(pickNumber({ a: "Infinity" }, ["a"])).toBeUndefined();
    expect(pickNumber({}, ["a"])).toBeUndefined();
  });
});

describe("durationMs", () => {
  it("subtracts two nanosecond timestamps", () => {
    expect(durationMs("1700000000000000000", "1700000000120000000")).toBe(120);
  });

  it("returns undefined when it cannot, rather than a negative number", () => {
    expect(durationMs("1700000000120000000", "1700000000000000000")).toBeUndefined();
    expect(durationMs(undefined, "1")).toBeUndefined();
    expect(durationMs("1", undefined)).toBeUndefined();
  });
});

describe("statusName and kindName", () => {
  it("reads the JSON mapping's enum names and numbers", () => {
    const span = (status: OtlpSpan["status"], kind: OtlpSpan["kind"]): OtlpSpan => ({
      traceId: "0".repeat(32),
      spanId: "0".repeat(16),
      name: "s",
      status,
      kind,
    });
    expect(statusName(span({ code: 1 }, 1))).toBe("STATUS_CODE_OK");
    expect(statusName(span({ code: "ERROR" }, 1))).toBe("STATUS_CODE_ERROR");
    expect(statusName(span({}, 1))).toBe("STATUS_CODE_UNSET");
    expect(statusName(span({ code: 99 }, 1))).toBe("STATUS_CODE_UNSET");
    expect(kindName(span({}, 2))).toBe("SPAN_KIND_SERVER");
    expect(kindName(span({}, "SPAN_KIND_CLIENT"))).toBe("SPAN_KIND_CLIENT");
    expect(kindName(span({}, 99))).toBe("SPAN_KIND_UNSPECIFIED");
    expect(kindName(span({}, "NOPE"))).toBe("SPAN_KIND_UNSPECIFIED");
  });
});
