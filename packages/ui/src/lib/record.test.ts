import { describe, expect, it } from "vitest";
import { asRecord, isRecord } from "./record";

describe("isRecord", () => {
  it("accepts plain objects, including empty and nested ones", () => {
    expect(isRecord({})).toBe(true);
    expect(isRecord({ a: 1 })).toBe(true);
    expect(isRecord({ a: { b: [1] } })).toBe(true);
  });

  it("rejects arrays: every caller reads a named key, and an array has none", () => {
    expect(isRecord([])).toBe(false);
    expect(isRecord([{ a: 1 }])).toBe(false);
  });

  it("rejects null, undefined and primitives", () => {
    expect(isRecord(null)).toBe(false);
    expect(isRecord(undefined)).toBe(false);
    expect(isRecord(0)).toBe(false);
    expect(isRecord(1)).toBe(false);
    expect(isRecord("")).toBe(false);
    expect(isRecord("{}")).toBe(false);
    expect(isRecord(true)).toBe(false);
    expect(isRecord(false)).toBe(false);
  });
});

describe("asRecord", () => {
  it("returns the same object reference for a record", () => {
    const value = { a: 1 };
    expect(asRecord(value)).toBe(value);
    expect(asRecord(value)?.a).toBe(1);
  });

  it("returns null for everything that is not a record", () => {
    expect(asRecord(null)).toBeNull();
    expect(asRecord(undefined)).toBeNull();
    expect(asRecord([])).toBeNull();
    expect(asRecord([1, 2])).toBeNull();
    expect(asRecord(0)).toBeNull();
    expect(asRecord("")).toBeNull();
    expect(asRecord('{"a":1}')).toBeNull();
    expect(asRecord(true)).toBeNull();
  });

  it("does not deep-copy, so nested reads need their own narrowing", () => {
    const nested = asRecord({ error: { message: "boom" } });
    expect(nested?.error).toEqual({ message: "boom" });
    expect(asRecord(nested?.error)?.message).toBe("boom");
  });
});
