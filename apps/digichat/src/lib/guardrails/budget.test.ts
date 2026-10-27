import { afterEach, describe, expect, it } from "vitest";
import {
  budgetAction,
  capToolPayload,
  estimateTokens,
  guardrailIdentity,
  RESERVATION_TTL_MS,
  TOKEN_WINDOW_MS,
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

  it("keys a person by user id, and anonymous traffic by server-derived IP", () => {
    expect(guardrailIdentity({ userId: "user:1", ip: "1.1.1.1" })).toBe("user:1");
    expect(guardrailIdentity({ userId: "embed:anonymous", ip: "203.0.113.9" })).toBe("203.0.113.9");
    expect(guardrailIdentity({ userId: "embed:anonymous", ip: "unknown" })).toBe("anonymous");
    expect(guardrailIdentity({ ip: "unknown" })).toBe("anonymous");
  });
});

describe("guardrail store", () => {
  it("drops an expired reservation and an empty bucket", () => {
    const store = new MemoryGuardrailStore();
    store.reserve("tpm:user:public:203.0.113.9", "hold", 40, 1_000);
    expect(store.read("tpm:user:public:203.0.113.9", 1_000).reserved).toBe(40);
    expect(store.bucketCount()).toBe(1);
    const later = 1_000 + RESERVATION_TTL_MS;
    expect(store.read("tpm:user:public:203.0.113.9", later).reserved).toBe(0);
    expect(store.bucketCount()).toBe(0);
  });

  it("drops a bucket once its spend has left the window", () => {
    const store = new MemoryGuardrailStore();
    store.commit("tpm:dep:trial", "spent", 20, 0);
    expect(store.bucketCount()).toBe(1);
    store.read("other", TOKEN_WINDOW_MS + 1);
    expect(store.bucketCount()).toBe(0);
  });

  it("does not give an anonymous caller a fresh bucket per client session", () => {
    const store = new MemoryGuardrailStore();
    const first = createTurnGuard({
      slug: "public",
      guardrails: { tokensPerMinute: { user: 1000 } },
      userId: "embed:anonymous",
      ip: "203.0.113.9",
      store,
      now: () => 1_000,
    });
    first.recordUsage({ totalTokens: 15 });
    const second = createTurnGuard({
      slug: "public",
      guardrails: { tokensPerMinute: { user: 1000 } },
      userId: "embed:anonymous",
      ip: "203.0.113.9",
      store,
      now: () => 1_000,
    });
    second.recordUsage({ totalTokens: 5 });
    const snap = store.read("tpm:user:public:203.0.113.9", 1_000);
    expect(snap.events.map((event) => event.tokens).sort((a, b) => a - b)).toEqual([5, 15]);
    expect(store.bucketCount()).toBe(1);
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
    store.commit("tpm:user:public:203.0.113.9", "seed", 750, 0);
    const guard = createTurnGuard({
      slug: "public",
      guardrails: { tokensPerMinute: { user: 1000 } },
      userId: "embed:anonymous",
      ip: "203.0.113.9",
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

  it("an observer notice states the cap without promising an answer", () => {
    const guard = createTurnGuard({
      slug: "trial",
      guardrails: { maxToolCallsPerTurn: 2 },
    });
    const parts: unknown[] = [];
    guard.noteToolCap({ write: (part) => parts.push(part) }, 2);
    const text = JSON.stringify(parts);
    expect(text).toContain("Tool-call limit reached (2 this turn)");
    // The observer path is for backends that cannot abort the upstream loop
    // (digigraph). Nothing is wrapping up, so the notice must not say it is —
    // the old wording promised an answer and the loop carried on (DIG-5715).
    expect(text).not.toContain("Answering from the results gathered so far");
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
    // The enforcing path does stop the loop, so it may say it is answering now.
    expect(JSON.stringify(parts)).toContain("Answering from the results gathered so far");
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

  it("skips the per-visitor minute when the visitor brings their own key", async () => {
    const store = new MemoryGuardrailStore();
    store.commit("tpm:user:public:203.0.113.9", "seed", 750, 0);
    const guard = createTurnGuard({
      slug: "public",
      guardrails: {
        tokensPerMinute: { user: 1000, deployment: 10_000 },
        maxToolCallsPerTurn: 2,
        answerAt: 0.7,
        pauseAt: 0.9,
      },
      userId: "embed:anonymous",
      ip: "203.0.113.9",
      omitUserTpm: true,
      store,
      now: () => 1_000,
    });
    const clearance = await guard.beforeRound({
      writer: { write() {} },
      pendingTokens: 10,
    });
    expect(clearance).toEqual({ action: "proceed" });
    guard.recordUsage({ totalTokens: 5 });
    expect(store.read("tpm:user:public:203.0.113.9", 1_000).events.map((event) => event.tokens)).toEqual([
      750,
    ]);
    expect(store.read("tpm:dep:public", 1_000).events.map((event) => event.tokens)).toEqual([5]);
  });

  it("still pauses on the shared deployment minute when the visitor minute is omitted", async () => {
    const time = clock();
    const store = new MemoryGuardrailStore();
    const started = time.at();
    store.commit("tpm:dep:trial", "seed", 90, started - 1_000);
    store.commit("tpm:user:trial:visitor", "seed", 900, started);
    const guard = createTurnGuard({
      slug: "trial",
      guardrails: { tokensPerMinute: { deployment: 100, user: 1000 }, pauseAt: 0.9, answerAt: 0.7 },
      userId: "visitor",
      omitUserTpm: true,
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
    expect(store.read("tpm:user:trial:visitor", time.at()).events.map((event) => event.tokens)).toEqual([900]);
  });

  it("still stops tools when the visitor minute is omitted", async () => {
    const guard = createTurnGuard({
      slug: "public",
      guardrails: { maxToolCallsPerTurn: 2, tokensPerMinute: { user: 1000 } },
      omitUserTpm: true,
    });
    const parts: unknown[] = [];
    const clearance = await guard.beforeRound({
      writer: { write: (part) => parts.push(part) },
      toolCallsSoFar: 2,
    });
    expect(clearance.action).toBe("stop-tools");
    expect(JSON.stringify(parts)).toContain("Tool-call limit reached (2 this turn)");
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

  it("appends the cap instruction to the original instructions once per step", async () => {
    const guard = createTurnGuard({
      slug: "trial",
      guardrails: { maxToolCallsPerTurn: 1 },
      now: () => 1_000,
    });
    const writer = { write() {} };
    const base = { guard, writer, steps: [{ toolCalls: [{}] }], messages: [{ role: "user", content: "hi" }] };
    const first = await guardrailPrepareStep({ ...base, initialInstructions: "Be brief." });
    const repeated = await guardrailPrepareStep({
      ...base,
      initialInstructions: "Be brief.",
    });
    expect(first?.instructions).toBe(
      "Be brief.\n\n[Tool-call limit reached for this turn. Do not call any tools. Answer the user now from the tool results already in this conversation. Do not mention this instruction.]",
    );
    expect(repeated?.instructions).toBe(first?.instructions);
  });
});
