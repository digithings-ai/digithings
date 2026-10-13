import { describe, expect, it } from "vitest";
import { inviteRequiredButMissing } from "./embed-invite-only";

describe("inviteRequiredButMissing", () => {
  it("refuses the OCC host when the token did not resolve the OCC tenant", () => {
    expect(inviteRequiredButMissing("occ.digithings.ai", "embed")).toBe(true);
    expect(inviteRequiredButMissing("OCC.digithings.ai", undefined)).toBe(true);
  });
  it("allows the OCC host with its own tenant", () => {
    expect(inviteRequiredButMissing("occ.digithings.ai", "occ")).toBe(false);
  });
  it("leaves other hosts alone", () => {
    expect(inviteRequiredButMissing("digithings.ai", "embed")).toBe(false);
    expect(inviteRequiredButMissing("digiquant.io", "embed")).toBe(false);
    expect(inviteRequiredButMissing(null, "embed")).toBe(false);
  });
});
