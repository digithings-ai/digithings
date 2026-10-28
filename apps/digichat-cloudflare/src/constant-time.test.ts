import { describe, expect, it } from "vitest";
import { constantTimeEqual } from "./constant-time";

describe("constantTimeEqual", () => {
  it("is true only for identical strings", () => {
    expect(constantTimeEqual("abc", "abc")).toBe(true);
    expect(constantTimeEqual("abc", "abd")).toBe(false);
    expect(constantTimeEqual("abc", "ab")).toBe(false);
    expect(constantTimeEqual("é", "e\u0301")).toBe(false);
  });
});
