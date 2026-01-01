import { afterEach, describe, expect, it } from "vitest";
import { admitChatTurn } from "./admit";
import { pricesFromCatalog } from "./prices";
import type { LimitsConfig } from "./schema";
import { resetLimitsStoreForTests, usdForTokens } from "./store";

const prices = {
  "deepseek/deepseek-v4.1-flash-1017": { inputPerM: 0.075, outputPerM: 0.3 },
  "openai/gpt-6.1-sol": { inputPerM: 1.5, outputPerM: 7.77 },
};

const base = {
  slug: "public",
  userId: "user-1",
  sessionId: "sess-1",
  ip: "203.0.113.9",
  explicitModel: false,
  prices,
  now: Date.parse("2026-10-21T12:00:00Z"),
};

afterEach(() => {
  resetLimitsStoreForTests();
});

describe("limit evaluation", () => {
  it("reads catalog prices and ignores a row with no id", () => {
    expect(
      pricesFromCatalog({
        models: [
          { id: "openai/gpt-6.1-sol", inputPerM: 1.5, outputPerM: 7.77 },
          { inputPerM: 1, outputPerM: 1 },
          { id: "bad", inputPerM: "1", outputPerM: 1 },
        ],
      }),
    ).toEqual({ "openai/gpt-6.1-sol": { inputPerM: 1.5, outputPerM: 7.77 } });
  });

  it("prices a premium model higher than the standard model for the same tokens", () => {
    const usage = { inputTokens: 8_000, outputTokens: 2_000 };
    const cheap = usdForTokens(usage, prices["deepseek/deepseek-v4.1-flash-1017"]);
    const premium = usdForTokens(usage, prices["openai/gpt-6.1-sol"]);
    expect(premium).toBeGreaterThan(cheap * 10);
  });

  it("blocks a second chat from one IP and does not spend the question cap on it", () => {
    const limits: LimitsConfig = {
      sessions: { perIp: { max: 1, window: "concurrent", message: "one chat" } },
      turns: { perDay: { ip: { max: 2, message: "questions" } } },
    };
    expect(admitChatTurn({ ...base, limits, conversationId: "conv-a" }).decision.action).toBe("proceed");
    expect(admitChatTurn({ ...base, limits, conversationId: "conv-b" }).decision).toMatchObject({
      action: "block",
      path: "limits.sessions.perIp",
      message: "one chat",
    });
    // The rejected chat was not counted, so the open chat still has a question left.
    expect(admitChatTurn({ ...base, limits, conversationId: "conv-a" }).decision.action).toBe("proceed");
    expect(admitChatTurn({ ...base, limits, conversationId: "conv-a" }).decision).toMatchObject({
      action: "block",
      path: "limits.turns.perDay.ip",
    });
  });

  it("skips an IP gate when the address is unknown", () => {
    const limits: LimitsConfig = { sessions: { perIp: { max: 1 } } };
    const first = admitChatTurn({ ...base, ip: "unknown", limits, conversationId: "conv-a" });
    const second = admitChatTurn({ ...base, ip: "unknown", limits, conversationId: "conv-b" });
    expect(first.decision.action).toBe("proceed");
    expect(second.decision.action).toBe("proceed");
  });

  it("falls back from an implicit premium pick and still charges the cost budget", () => {
    const limits: LimitsConfig = {
      models: {
        standard: { maxOutputUsdPerMillion: 2 },
        premium: { manualOnly: true, onExceed: "fallback-auto" },
      },
      cost: { usd: { perDay: { user: { max: 0.02, onExceed: "block", message: "budget" } } } },
    };
    const implicit = admitChatTurn({
      ...base,
      limits,
      modelId: "openai/gpt-6.1-sol",
      explicitModel: false,
      autoModel: "deepseek/deepseek-v4.1-flash-1017",
    });
    expect(implicit.decision.action).toBe("fallback-auto");
    expect(implicit.model).toBe("deepseek/deepseek-v4.1-flash-1017");

    const explicit = admitChatTurn({
      ...base,
      limits,
      modelId: "openai/gpt-6.1-sol",
      explicitModel: true,
      autoModel: "deepseek/deepseek-v4.1-flash-1017",
    });
    expect(explicit.decision.action).toBe("proceed");
    explicit.record({ inputTokens: 20_000, outputTokens: 4_000 }, "openai/gpt-6.1-sol");

    const over = admitChatTurn({
      ...base,
      limits,
      modelId: "deepseek/deepseek-v4.1-flash-1017",
      explicitModel: true,
      autoModel: "deepseek/deepseek-v4.1-flash-1017",
    });
    expect(over.decision).toMatchObject({ action: "block", path: "limits.cost.usd.perDay.user" });
  });

  it("lets a cheap model take more turns than a premium model on the same budget", () => {
    const limits: LimitsConfig = {
      cost: { usd: { perDay: { user: { max: 0.01, onExceed: "block" } } } },
    };
    const usage = { inputTokens: 1_000, outputTokens: 4_000 };
    let cheapTurns = 0;
    for (let i = 0; i < 20; i++) {
      const turn = admitChatTurn({
        ...base,
        limits,
        modelId: "deepseek/deepseek-v4.1-flash-1017",
        explicitModel: true,
        conversationId: "conv-cheap",
      });
      if (turn.decision.action !== "proceed") break;
      turn.record(usage, "deepseek/deepseek-v4.1-flash-1017");
      cheapTurns += 1;
    }
    resetLimitsStoreForTests();
    let premiumTurns = 0;
    for (let i = 0; i < 20; i++) {
      const turn = admitChatTurn({
        ...base,
        limits,
        modelId: "openai/gpt-6.1-sol",
        explicitModel: true,
        conversationId: "conv-premium",
      });
      if (turn.decision.action !== "proceed") break;
      turn.record(usage, "openai/gpt-6.1-sol");
      premiumTurns += 1;
    }
    expect(cheapTurns).toBeGreaterThan(premiumTurns);
    expect(premiumTurns).toBe(1);
  });

  it("pauses a turn limit by asking for a summary instead of blocking", () => {
    const limits: LimitsConfig = {
      turns: { perSession: { session: { max: 1, onExceed: "pause", message: "summarize" } } },
    };
    const first = admitChatTurn({ ...base, limits, conversationId: "conv-1" });
    expect(first.decision.action).toBe("proceed");
    const second = admitChatTurn({ ...base, limits, conversationId: "conv-1" });
    expect(second.decision).toMatchObject({ action: "pause", message: "summarize" });
    expect(second.summarize?.instruction).toMatch(/short summary/);
  });

  it("does not block a token-per-minute pause in the pre-check", () => {
    const limits: LimitsConfig = {
      tokens: { total: { perMinute: { user: { max: 10, onExceed: "pause" } } } },
    };
    const turn = admitChatTurn({ ...base, limits, conversationId: "conv-1" });
    expect(turn.decision.action).toBe("proceed");
    turn.record({ totalTokens: 10_000 }, "deepseek/deepseek-v4.1-flash-1017");
    const next = admitChatTurn({ ...base, limits, conversationId: "conv-1" });
    expect(next.decision.action).toBe("proceed");
  });

  it("blocks a per-day token cap after the recorded usage crosses it", () => {
    const limits: LimitsConfig = {
      tokens: { total: { perDay: { user: { max: 100, onExceed: "block", message: "daily tokens" } } } },
    };
    const turn = admitChatTurn({ ...base, limits });
    turn.record({ inputTokens: 80, outputTokens: 30 });
    const next = admitChatTurn({ ...base, limits });
    expect(next.decision).toMatchObject({ action: "block", message: "daily tokens" });
  });

  it("meters models.costPerWindow as premium-only and lets the window roll off", () => {
    const costPerWindow = { usd: 0.02, windowSeconds: 86_400 };
    const first = admitChatTurn({
      ...base,
      costPerWindow,
      outputCapUsdPerMillion: 2,
      modelId: "openai/gpt-6.1-sol",
      explicitModel: true,
      autoModel: "deepseek/deepseek-v4.1-flash-1017",
    });
    expect(first.decision.action).toBe("proceed");
    first.record({ inputTokens: 20_000, outputTokens: 4_000 }, "openai/gpt-6.1-sol");
    const cheap = admitChatTurn({
      ...base,
      costPerWindow,
      outputCapUsdPerMillion: 2,
      modelId: "deepseek/deepseek-v4.1-flash-1017",
      explicitModel: true,
    });
    expect(cheap.decision.action).toBe("proceed");
    const premium = admitChatTurn({
      ...base,
      costPerWindow,
      outputCapUsdPerMillion: 2,
      modelId: "openai/gpt-6.1-sol",
      explicitModel: true,
      autoModel: "deepseek/deepseek-v4.1-flash-1017",
    });
    expect(premium.decision.action).toBe("fallback-auto");
    const later = admitChatTurn({
      ...base,
      now: base.now + 86_400_000,
      costPerWindow,
      outputCapUsdPerMillion: 2,
      modelId: "openai/gpt-6.1-sol",
      explicitModel: true,
    });
    expect(later.decision.action).toBe("proceed");
  });

  it("does not charge a standard model against a premium-only budget", () => {
    const limits: LimitsConfig = {
      models: { standard: { maxOutputUsdPerMillion: 2 }, premium: { manualOnly: true } },
      cost: {
        usd: { perDay: { user: { max: 0.0001, premiumOnly: true, onExceed: "block" } } },
      },
    };
    const turn = admitChatTurn({
      ...base,
      limits,
      modelId: "deepseek/deepseek-v4.1-flash-1017",
      explicitModel: true,
    });
    turn.record({ inputTokens: 100_000, outputTokens: 100_000 }, "deepseek/deepseek-v4.1-flash-1017");
    const next = admitChatTurn({
      ...base,
      limits,
      modelId: "deepseek/deepseek-v4.1-flash-1017",
      explicitModel: true,
    });
    expect(next.decision.action).toBe("proceed");
  });

  it("keeps two IPs on separate session slots", () => {
    const limits: LimitsConfig = { sessions: { perIp: { max: 1, window: "day" } } };
    admitChatTurn({ ...base, limits, conversationId: "a" });
    const other = admitChatTurn({ ...base, ip: "203.0.113.10", limits, conversationId: "b" });
    expect(other.decision.action).toBe("proceed");
    const again = admitChatTurn({ ...base, limits, conversationId: "c" });
    expect(again.decision.action).toBe("block");
  });
});
