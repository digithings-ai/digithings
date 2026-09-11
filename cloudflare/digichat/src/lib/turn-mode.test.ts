import { describe, expect, it } from "vitest";
import { isMutatingTurnMode, parseDigiTurnMode } from "./turn-mode";

describe("parseDigiTurnMode", () => {
  it("defaults missing/blank to send", () => {
    expect(parseDigiTurnMode(null)).toBe("send");
    expect(parseDigiTurnMode(undefined)).toBe("send");
    expect(parseDigiTurnMode("")).toBe("send");
    expect(parseDigiTurnMode("  ")).toBe("send");
  });

  it("accepts the three contract modes case-insensitively", () => {
    expect(parseDigiTurnMode("send")).toBe("send");
    expect(parseDigiTurnMode("Regenerate")).toBe("regenerate");
    expect(parseDigiTurnMode("EDIT_LAST_USER")).toBe("edit_last_user");
  });

  it("rejects unknown values", () => {
    expect(parseDigiTurnMode("fork")).toBe("invalid");
    expect(parseDigiTurnMode("retry")).toBe("invalid");
  });
});

describe("isMutatingTurnMode", () => {
  it("is true only for regenerate and edit_last_user", () => {
    expect(isMutatingTurnMode("send")).toBe(false);
    expect(isMutatingTurnMode("regenerate")).toBe(true);
    expect(isMutatingTurnMode("edit_last_user")).toBe(true);
  });
});
