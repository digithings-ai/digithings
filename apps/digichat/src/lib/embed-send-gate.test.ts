import { describe, expect, it } from "vitest";
import {
  decideEmbedSendGate,
  shouldArmGateCharge,
} from "./embed-send-gate";

describe("decideEmbedSendGate", () => {
  it("allows send when ungated", () => {
    expect(
      decideEmbedSendGate({
        locked: true,
        trialLocked: true,
        ungated: true,
        byokRequired: false,
      }),
    ).toEqual({ action: "send" });
  });

  it("holds for gate when turn-limited and locked", () => {
    expect(
      decideEmbedSendGate({
        locked: true,
        trialLocked: false,
        ungated: false,
        byokRequired: false,
      }),
    ).toEqual({ action: "hold_gate" });
  });

  it("holds for gate when trialLocked", () => {
    expect(
      decideEmbedSendGate({
        locked: false,
        trialLocked: true,
        ungated: false,
        byokRequired: false,
      }),
    ).toEqual({ action: "hold_gate" });
  });

  it("holds for BYOK before gate when byok_only without key", () => {
    expect(
      decideEmbedSendGate({
        locked: true,
        trialLocked: false,
        ungated: false,
        byokRequired: true,
      }),
    ).toEqual({ action: "hold_byok" });
  });

  it("allows send on open free tier", () => {
    expect(
      decideEmbedSendGate({
        locked: false,
        trialLocked: false,
        ungated: false,
        byokRequired: false,
      }),
    ).toEqual({ action: "send" });
  });
});

describe("shouldArmGateCharge", () => {
  it("arms when gated tenant", () => {
    expect(shouldArmGateCharge(false)).toBe(true);
  });

  it("skips arm when ungated", () => {
    expect(shouldArmGateCharge(true)).toBe(false);
  });
});
