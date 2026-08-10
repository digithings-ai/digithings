import { describe, expect, it } from "vitest";
import { byokActivationGate } from "@/lib/byok-ping";

describe("byok-ping activation gate", () => {
  it("blocks activation until a successful ping", () => {
    expect(byokActivationGate(null)).not.toBeNull();
    expect(byokActivationGate({ ok: false, error: "denied" })).toBe("denied");
    expect(byokActivationGate({ ok: true })).toBeNull();
  });
});
