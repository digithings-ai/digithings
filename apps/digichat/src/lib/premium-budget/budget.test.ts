import { describe, expect, it, beforeEach } from "vitest";
import catalogJson from "../../../config/model-picker-catalog.json";
import {
  PEER_IP_HEADER,
  PEER_STAMP_HEADER,
  clientIpForRateLimit,
} from "@/lib/embed-ip-rate-limit";
import {
  PREMIUM_BUDGET_MESSAGE,
  PREMIUM_BUDGET_TURNS,
  TYPICAL_PREMIUM_INPUT_TOKENS,
  TYPICAL_PREMIUM_OUTPUT_TOKENS,
  applyPremiumBudget,
  chargePremiumUsage,
  premiumSpendIdentity,
  premiumTurnUsd,
  premiumUserKey,
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

  it("drops to Auto when the budget is spent and no default is configured", () => {
    const rate = { inputPerM: glm!.inputPerM, outputPerM: glm!.outputPerM };
    const now = Date.now();
    chargePremiumUsage("digithings:anon", rate, undefined, now);
    chargePremiumUsage("digithings:anon", rate, undefined, now);
    chargePremiumUsage("digithings:anon", rate, undefined, now);
    const blocked = applyPremiumBudget({
      modelId: "z-ai/glm-5.3",
      defaultModel: undefined,
      premium: true,
      rate,
      budget: { usd: 0.0125565, windowSeconds: 86_400 },
      userKey: "digithings:anon",
      nowMs: Date.now(),
    });
    expect(blocked.modelId).toBe("deepseek/deepseek-v4.1-flash-1017");
    expect(blocked.modelId).not.toBe("z-ai/glm-5.3");
    expect(blocked.notice).toBe(PREMIUM_BUDGET_MESSAGE);
  });

  it("drops to Auto when the configured default is itself premium", () => {
    const rate = { inputPerM: glm!.inputPerM, outputPerM: glm!.outputPerM };
    const now = Date.now();
    chargePremiumUsage("digithings:anon", rate, undefined, now);
    chargePremiumUsage("digithings:anon", rate, undefined, now);
    chargePremiumUsage("digithings:anon", rate, undefined, now);
    const blocked = applyPremiumBudget({
      modelId: "z-ai/glm-5.3",
      defaultModel: "google/gemini-3.8-flash",
      premium: true,
      premiumIds: ["google/gemini-3.8-flash", "z-ai/glm-5.3"],
      rate,
      budget: { usd: 0.0125565, windowSeconds: 86_400 },
      userKey: "digithings:anon",
      nowMs: Date.now(),
    });
    expect(blocked.modelId).toBe("deepseek/deepseek-v4.1-flash-1017");
    expect(blocked.modelId).not.toBe("google/gemini-3.8-flash");
    expect(blocked.notice).toBe(PREMIUM_BUDGET_MESSAGE);
    expect(blocked.notice).toMatch(/Answering with Auto instead/);
  });

  it("keeps rotating X-Forwarded-For values on one budget key", () => {
    delete process.env.DIGICHAT_TRUSTED_PROXIES;
    delete process.env.DIGICHAT_PEER_STAMP;
    try {
      const keyFor = (xff: string, peer?: string, stamp?: string) => {
        const headers: Record<string, string> = { "x-forwarded-for": xff };
        if (peer) headers[PEER_IP_HEADER] = peer;
        if (stamp) headers[PEER_STAMP_HEADER] = stamp;
        // A bare peer has no stamp, so forwarded headers stay spoofable and
        // must not open a budget key. A matching stamp is the socket.
        if (!stamp) headers["cf-connecting-ip"] = xff.split(",")[0]?.trim() ?? "";
        const ip = clientIpForRateLimit(new Request("http://localhost/api/chat", { headers }));
        return premiumUserKey("public", premiumSpendIdentity({ userId: "embed:anonymous", ip }));
      };
      const forwarded = ["198.51.100.1", "198.51.100.2, 10.0.0.1", "203.0.113.50"];
      const unsigned = forwarded.map((xff) => keyFor(xff));
      expect(new Set(unsigned).size).toBe(1);
      expect(unsigned[0]).toBe("public:anonymous");

      const barePeer = forwarded.map((xff) => keyFor(xff, "203.0.113.7"));
      expect(new Set(barePeer).size).toBe(1);
      expect(barePeer[0]).toBe("public:anonymous");

      process.env.DIGICHAT_PEER_STAMP = "stamp-secret";
      const stamped = forwarded.map((xff) => keyFor(xff, "203.0.113.7", "stamp-secret"));
      expect(new Set(stamped).size).toBe(1);
      expect(stamped[0]).toBe("public:203.0.113.7");

      const rate = { inputPerM: glm!.inputPerM, outputPerM: glm!.outputPerM };
      const now = Date.now();
      for (const key of stamped) chargePremiumUsage(key, rate, undefined, now);
      const shared = applyPremiumBudget({
        modelId: "z-ai/glm-5.3",
        premium: true,
        rate,
        budget: { usd: 0.0125565, windowSeconds: 86_400 },
        userKey: stamped[0]!,
        nowMs: Date.now(),
      });
      expect(shared.modelId).toBe("deepseek/deepseek-v4.1-flash-1017");
      const spoofed = applyPremiumBudget({
        modelId: "z-ai/glm-5.3",
        premium: true,
        rate,
        budget: { usd: 0.0125565, windowSeconds: 86_400 },
        userKey: "public:198.51.100.1",
        nowMs: Date.now(),
      });
      expect(spoofed.notice).toBeUndefined();
      expect(spoofed.modelId).toBe("z-ai/glm-5.3");
    } finally {
      delete process.env.DIGICHAT_PEER_STAMP;
      delete process.env.DIGICHAT_TRUSTED_PROXIES;
    }
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
