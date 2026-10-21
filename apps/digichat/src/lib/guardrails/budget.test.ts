import { afterEach, describe, expect, it } from "vitest";
import {
  budgetAction,
  capToolPayload,
  estimateTokens,
  guardrailIdentity,
  tokensInWindow,
  truncateToTokens,
  waitForRoomMs,
  WRAP_UP_INSTRUCTION,
} from "./budget";
import {
  installGuardrailStore,
  MemoryGuardrailStore,
  resetGuardrailStoreForTests,
} from "./store";
import { createTurnGuard, guardrailPrepareStep, resolveGuardrails } from "./turn";

afterEach(() => {
  resetGuardrailStoreForTests();
});

describe("token budget decisions", () => {
  it("estimates pending text and ignores an empty string", () => {
    expect(estimateTokens("")).toBe(0);
    expect(estimateTokens("abcd")).toBe(1);
    expect(estimateTokens("abcde")).toBe(2);
  });

  it("drops spend older than 60 seconds", () => {
    const events = [
      { at: 0, tokens: 500 },
      { at: 30_000, tokens: 100 },
    ];
    expect(tokensInWindow(events, 60_000)).toBe(100);
    expect(tokensInWindow(events, 90_000)).toBe(0);
  });

  it("proceeds under answerAt, nudges in the band, and pauses at the ceiling", () => {
    const base = { reserved: 0, pending: 10, limit: 100, answerAt: 0.7, pauseAt: 0.9 };
    expect(budgetAction({ ...base, used: 50 })).toBe("proceed");
    expect(budgetAction({ ...base, used: 75 })).toBe("answer");
    expect(budgetAction({ ...base, used: 90 })).toBe("pause");
    expect(budgetAction({ ...base, used: 50, pending: 60 })).toBe("pause");
  });

  it("waits until the spend that is blocking the round expires", () => {
    const events = [{ at: 1_000, tokens: 90 }];
    const wait = waitForRoomMs({
      events,
      reserved: 0,
      pending: 20,
      limit: 100,
      pauseAt: 0.9,
      now: 10_000,
    });
    expect(wait).toBe(1_000 + 60_000 - 10_000);
    expect(
      waitForRoomMs({
        events: [],
        reserved: 0,
        pending: 200,
        limit: 100,
        pauseAt: 0.9,
        now: 0,
      }),
    ).toBe(0);
  });

  it("truncates a tool result to the remaining budget", () => {
    expect(truncateToTokens("abcdef", 1)).toBe("abcd\n…[truncated to the token budget]");
    expect(capToolPayload({ rows: "abcdef" }, 1)).toEqual({
      truncated: '{"ro\n…[truncated to the token budget]',
    });
    expect(capToolPayload("ok", 10)).toBe("ok");
  });

  it("keys a person by user id, then session, then IP", () => {
    expect(guardrailIdentity({ userId: "user:1", sessionId: "s", ip: "1.1.1.1" })).toBe("user:1");
    expect(guardrailIdentity({ userId: "embed:anonymous", sessionId: "s", ip: "1.1.1.1" })).toBe("s");
    expect(guardrailIdentity({ userId: "embed:anonymous", ip: "1.1.1.1" })).toBe("1.1.1.1");
    expect(guardrailIdentity({ userId: "embed:anonymous", ip: "unknown" })).toBe("anonymous");
  });
});

describe("resolveGuardrails", () => {
  it("is off when nothing is set", () => {
    expect(resolveGuardrails(undefined, undefined)).toBeNull();
    expect(resolveGuardrails({ answerAt: 0.5 }, undefined)).toBeNull();
  });

  it("prefers the shared tool cap and still accepts the Foundry alias", () => {
    expect(resolveGuardrails({ maxToolCallsPerTurn: 4 }, 9)?.maxToolCallsPerTurn).toBe(4);
    expect(resolveGuardrails(undefined, 5)?.maxToolCallsPerTurn).toBe(5);
  });

  it("defaults the fractions when a TPM is set", () => {
    const resolved = resolveGuardrails({ tokensPerMinute: { user: 80_000 } });
    expect(resolved).toMatchObject({
      userTokensPerMinute: 80_000,
      answerAt: 0.7,
      pauseAt: 0.9,
    });
  });
});

describe("createTurnGuard", () => {
  function clock() {
    let now = 1_000_000;
    return {
      now: () => now,
      sleep: async (ms: number) => {
        now += ms;
      },
      at: () => now,
    };
  }

  it("pauses on the shared waiter, then continues and records reported usage", async () => {
    const time = clock();
    const store = new MemoryGuardrailStore();
    store.commit("tpm:dep:trial", "seed", 90, time.at() - 1_000);
    const guard = createTurnGuard({
      slug: "trial",
      guardrails: { tokensPerMinute: { deployment: 100 }, pauseAt: 0.9, answerAt: 0.7 },
      store,
      now: time.now,
      sleep: time.sleep,
    });
    const parts: unknown[] = [];
    const clearance = await guard.beforeRound({
      writer: { write: (part) => parts.push(part) },
      pendingText: "abcd",
    });
    expect(clearance.action).toBe("proceed");
    expect(JSON.stringify(parts)).toContain("Pausing for the token limit, resuming shortly");
    expect(JSON.stringify(parts)).toContain('"state":"ready"');
    guard.recordUsage({ inputTokens: 4, outputTokens: 6, totalTokens: 10 });
    expect(store.read("tpm:dep:trial", time.at()).reserved).toBe(0);
    expect(store.read("tpm:dep:trial", time.at()).events.some((event) => event.tokens === 10)).toBe(true);
  });

  it("nudges an answer between the thresholds without pausing", async () => {
    const store = new MemoryGuardrailStore();
    store.commit("tpm:user:public:s1", "seed", 750, 0);
    const guard = createTurnGuard({
      slug: "public",
      guardrails: { tokensPerMinute: { user: 1000 } },
      sessionId: "s1",
      userId: "embed:anonymous",
      store,
      now: () => 1_000,
    });
    const parts: unknown[] = [];
    const clearance = await guard.beforeRound({
      writer: { write: (part) => parts.push(part) },
      pendingTokens: 10,
    });
    expect(clearance).toEqual({ action: "answer", instruction: WRAP_UP_INSTRUCTION });
    expect(parts).toEqual([]);
  });

  it("stops further tools at the shared cap and does not throw", async () => {
    const guard = createTurnGuard({
      slug: "trial",
      guardrails: { maxToolCallsPerTurn: 2 },
    });
    const parts: unknown[] = [];
    const clearance = await guard.beforeRound({
      writer: { write: (part) => parts.push(part) },
      toolCallsSoFar: 2,
    });
    expect(clearance.action).toBe("stop-tools");
    expect(JSON.stringify(parts)).toContain("Tool-call limit reached (2 this turn)");
    expect(JSON.stringify(parts)).not.toContain('"type":"error"');
  });

  it("shares a window across turns on one store and not across stores", () => {
    const shared = new MemoryGuardrailStore();
    shared.commit("tpm:dep:trial", "a", 40, 500);
    const other = new MemoryGuardrailStore();
    expect(shared.read("tpm:dep:trial", 1_000).events).toHaveLength(1);
    expect(other.read("tpm:dep:trial", 1_000).events).toHaveLength(0);
    installGuardrailStore(shared);
    const guard = createTurnGuard({
      slug: "trial",
      guardrails: { tokensPerMinute: { deployment: 100 } },
      now: () => 1_000,
    });
    guard.recordUsage({ totalTokens: 15 });
    expect(shared.read("tpm:dep:trial", 1_000).events.map((event) => event.tokens)).toContain(15);
  });

  it("clips tool results and asks the model to stop once the cap is spent", async () => {
    const guard = createTurnGuard({
      slug: "trial",
      guardrails: { maxToolCallsPerTurn: 1, tokensPerMinute: { deployment: 100 } },
      now: () => 1_000,
    });
    const writer = { write() {} };
    const step = await guardrailPrepareStep({
      guard,
      writer,
      steps: [{ toolCalls: [{}] }],
      messages: [{ role: "tool", content: "x".repeat(10_000) }, { role: "user", content: "hi" }],
    });
    expect(step?.toolChoice).toBe("none");
    expect(step?.messages?.[0]?.content).toEqual(
      expect.stringContaining("truncated to the token budget"),
    );
  });
});
