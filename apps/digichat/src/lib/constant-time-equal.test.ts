import { describe, expect, it } from "vitest";
import { constantTimeEqual } from "./constant-time-equal";

describe("constantTimeEqual", () => {
  it("is true only for identical strings", () => {
    expect(constantTimeEqual("abc", "abc")).toBe(true);
    expect(constantTimeEqual("", "")).toBe(true);
    expect(constantTimeEqual("abc", "abd")).toBe(false);
    expect(constantTimeEqual("abc", "ab")).toBe(false);
    expect(constantTimeEqual("ab", "abc")).toBe(false);
  });

  it("compares UTF-8 bytes, not UTF-16 units", () => {
    expect(constantTimeEqual("é", "é")).toBe(true);
    expect(constantTimeEqual("é", "e\u0301")).toBe(false);
  });

});
