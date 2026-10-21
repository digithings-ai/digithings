import { describe, expect, it, afterEach } from "vitest";
import { digillmRouterOffered, latestUserText } from "./digillm-router";
import { withDigillmRouterNotice } from "./digillm-router-notice";
import {
  DigillmRouterUnavailable,
  routeWithDigillm,
  setDigillmRouterRunnerForTests,
} from "./digillm-router-process";

const decision = {
  routeId: "fast",
  label: "Fast",
  model: "deepseek/deepseek-v4.1-flash-1017",
  reason: "Short factual lookup.",
  confidence: 0.86,
};

afterEach(() => {
  setDigillmRouterRunnerForTests(null);
});

describe("digillm router offer", () => {
  it("is on only for backends that can apply a per-turn model", () => {
    expect(digillmRouterOffered({ enabled: true, backendType: "digigraph" })).toBe(true);
    expect(digillmRouterOffered({ enabled: true, backendType: "openai-responses" })).toBe(true);
    expect(digillmRouterOffered({ enabled: true, backendType: "foundry" })).toBe(false);
    expect(digillmRouterOffered({ enabled: false, backendType: "digigraph" })).toBe(false);
    expect(digillmRouterOffered({ enabled: undefined, backendType: "digigraph" })).toBe(false);
  });
});

describe("latest user text", () => {
  it("uses the last user text and ignores file parts", () => {
    const text = latestUserText([
      { role: "user", parts: [{ type: "text", text: "earlier" }] },
      { role: "assistant", parts: [{ type: "text", text: "reply" }] },
      {
        role: "user",
        parts: [
          { type: "file", text: "page context that must not route" },
          { type: "text", text: "What is the capital of France?" },
        ],
      },
    ]);
    expect(text).toBe("What is the capital of France?");
  });
});

describe("router notice", () => {
  it("inserts a status line after the first event and sets headers", async () => {
    const body = `data: ${JSON.stringify({ type: "start" })}\n\n`;
    const res = withDigillmRouterNotice(
      new Response(body, { headers: { "content-type": "text/event-stream" } }),
      decision,
    );
    const text = await res.text();
    expect(res.headers.get("x-digillm-router-route")).toBe("fast");
    expect(res.headers.get("x-digillm-router-model")).toBe(decision.model);
    expect(text.indexOf('"type":"start"')).toBeLessThan(text.indexOf("data-status"));
    expect(text).toContain(`Router · Fast · ${decision.model}`);
    expect(text).toContain("Short factual lookup.");
  });

  it("leaves a JSON body alone and still sets the headers", async () => {
    const res = withDigillmRouterNotice(
      new Response("{}", { headers: { "content-type": "application/json" } }),
      decision,
    );
    expect(await res.text()).toBe("{}");
    expect(res.headers.get("x-digillm-router-model")).toBe(decision.model);
  });
});

describe("router process", () => {
  it("uses the injected runner", async () => {
    setDigillmRouterRunnerForTests(async () => decision);
    await expect(
      routeWithDigillm({ text: "hi", allowed: [decision.model], fallback: decision.model }),
    ).resolves.toEqual(decision);
  });

  it("fails closed when the interpreter cannot be started", async () => {
    const previous = process.env.DIGILLM_PYTHON;
    process.env.DIGILLM_PYTHON = "/no/such/digillm-python";
    try {
      await expect(
        routeWithDigillm({ text: "hi", allowed: [], fallback: "m" }),
      ).rejects.toBeInstanceOf(DigillmRouterUnavailable);
    } finally {
      if (previous === undefined) delete process.env.DIGILLM_PYTHON;
      else process.env.DIGILLM_PYTHON = previous;
    }
  });
});
