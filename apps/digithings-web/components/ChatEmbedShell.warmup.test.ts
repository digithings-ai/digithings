import { describe, expect, it } from "vitest";

import { WARMUP_PATH, waitForServices } from "./ChatEmbedShell";

function fakeFetch(bodies: unknown[]) {
  const calls: string[] = [];
  const impl = (async (url: string) => {
    calls.push(url);
    const body = bodies.shift() ?? { ready: false };
    if (body instanceof Error) throw body;
    return { json: async () => body } as Response;
  }) as unknown as typeof fetch;
  return { impl, calls };
}

describe("waitForServices", () => {
  it("polls the embed warm-up route until every service is ready", async () => {
    const seen: string[][] = [];
    const { impl, calls } = fakeFetch([
      { ready: false, services: { auth: "waking", assistant: "waking" } },
      new Error("probe timeout"),
      { ready: true, services: { auth: "ready", assistant: "ready" } },
    ]);
    const ok = await waitForServices("https://digithings.ai/", {
      isCancelled: () => false,
      onServices: (names) => seen.push(names),
      fetchImpl: impl,
      sleep: async () => {},
    });
    expect(ok).toBe(true);
    expect(calls).toEqual(Array(3).fill(`https://digithings.ai${WARMUP_PATH}`));
    expect(seen.at(-1)).toEqual(["auth", "assistant"]);
  });

  it("gives up after the budget so the chat is still revealed", async () => {
    let t = 0;
    const { impl } = fakeFetch([]);
    const ok = await waitForServices("https://digithings.ai", {
      isCancelled: () => false,
      fetchImpl: impl,
      budgetMs: 10_000,
      now: () => t,
      sleep: async (ms) => {
        t += ms;
      },
    });
    expect(ok).toBe(false);
  });

  it("stops when cancelled", async () => {
    const { impl, calls } = fakeFetch([]);
    const ok = await waitForServices("https://digithings.ai", {
      isCancelled: () => calls.length > 0,
      fetchImpl: impl,
      sleep: async () => {},
    });
    expect(ok).toBe(false);
    expect(calls).toHaveLength(1);
  });
});
