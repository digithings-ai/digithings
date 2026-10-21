import { describe, expect, it, beforeEach } from "vitest";
import catalogJson from "../../../config/model-picker-catalog.json";
import {
  PREMIUM_BUDGET_MESSAGE,
  PREMIUM_BUDGET_TURNS,
  TYPICAL_PREMIUM_INPUT_TOKENS,
  TYPICAL_PREMIUM_OUTPUT_TOKENS,
  applyPremiumBudget,
  premiumSpendIdentity,
  premiumTurnUsd,
  resetPremiumSpendForTests,
} from "./budget";

const glm = catalogJson.models.find((model) => model.id === "z-ai/glm-5.3");
const gemini = catalogJson.models.find((model) => model.id === "google/gemini-3.8-flash");

describe("premium spend budget", () => {
  beforeEach(() => {
    resetPremiumSpendForTests();
  });

  it("prices three typical turns of the pricier premium model at $0.0125565", () => {
    expect(glm).toBeTruthy();
    expect(gemini).toBeTruthy();
    const glmTurn = premiumTurnUsd({ inputPerM: glm!.inputPerM, outputPerM: glm!.outputPerM });
    const geminiTurn = premiumTurnUsd({
      inputPerM: gemini!.inputPerM,
      outputPerM: gemini!.outputPerM,
    });
    expect(glmTurn).toBeGreaterThan(geminiTurn);
    expect(glmTurn).toBeCloseTo(0.0041855, 8);
    expect(PREMIUM_BUDGET_TURNS * glmTurn).toBeCloseTo(0.0125565, 8);
    expect(TYPICAL_PREMIUM_INPUT_TOKENS).toBe(3550);
    expect(TYPICAL_PREMIUM_OUTPUT_TOKENS).toBe(600);
  });

  it("keys spend on the user, then the client IP, then a shared anonymous bucket", () => {
    expect(premiumSpendIdentity({ userId: "user-1", ip: "203.0.113.4" })).toBe("user-1");
    expect(premiumSpendIdentity({ userId: "embed:anonymous", ip: "203.0.113.4" })).toBe(
      "203.0.113.4",
    );
    expect(premiumSpendIdentity({ userId: "embed:anonymous", ip: "unknown" })).toBe("anonymous");
    expect(premiumSpendIdentity({})).toBe("anonymous");
  });

  it("allows premium until the rolling window is spent, then falls back to Auto", () => {
    const budget = { usd: 0.0125565, windowSeconds: 86_400 };
    const rate = { inputPerM: glm!.inputPerM, outputPerM: glm!.outputPerM };
    const base = {
      modelId: "z-ai/glm-5.3",
      defaultModel: "deepseek/deepseek-v4.1-flash-1017",
      premium: true,
      rate,
      budget,
      userKey: "digithings:session-1",
      nowMs: 1_000_000,
    };
    const now = Date.now();
    const first = applyPremiumBudget({ ...base, nowMs: now });
    expect(first.notice).toBeUndefined();
    expect(first.modelId).toBe("z-ai/glm-5.3");
    first.charge?.({ inputTokens: 3550, outputTokens: 600 });
    first.charge?.({ inputTokens: 3550, outputTokens: 600 });
    first.charge?.({ inputTokens: 3550, outputTokens: 600 });
    const blocked = applyPremiumBudget({ ...base, nowMs: Date.now() });
    expect(blocked.modelId).toBe("deepseek/deepseek-v4.1-flash-1017");
    expect(blocked.notice).toBe(PREMIUM_BUDGET_MESSAGE);
    expect(blocked.charge).toBeUndefined();
    const later = applyPremiumBudget({ ...base, nowMs: Date.now() + 86_400_000 + 1_000 });
    expect(later.notice).toBeUndefined();
    expect(later.modelId).toBe("z-ai/glm-5.3");
  });

  it("does not meter a preset or a deployment with no budget", () => {
    const open = applyPremiumBudget({
      modelId: "z-ai/glm-5.3",
      defaultModel: "deepseek/deepseek-v4.1-flash-1017",
      premium: true,
      rate: { inputPerM: 0.77, outputPerM: 2.42 },
      budget: undefined,
      userKey: "occ:session",
    });
    expect(open.notice).toBeUndefined();
    expect(open.charge).toBeUndefined();
    const preset = applyPremiumBudget({
      modelId: "z-ai/glm-5.3-flash",
      defaultModel: "deepseek/deepseek-v4.1-flash-1017",
      premium: false,
      rate: { inputPerM: 0.0825, outputPerM: 0.275 },
      budget: { usd: 0.0125565 },
      userKey: "digithings:session",
    });
    expect(preset.charge).toBeUndefined();
  });

  it("charges the real token mix, so a larger output spends the window faster", () => {
    const rate = { inputPerM: glm!.inputPerM, outputPerM: glm!.outputPerM };
    const light = premiumTurnUsd(rate, 3550, 600);
    const heavy = premiumTurnUsd(rate, 3550, 4000);
    expect(heavy).toBeGreaterThan(light * 2);
  });
});
