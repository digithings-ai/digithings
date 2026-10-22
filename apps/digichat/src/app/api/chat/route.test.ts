import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));

vi.mock("@/lib/chat-route-context", () => ({
  resolveChatTenantContext: vi.fn(),
}));

vi.mock("@/lib/bff-rate-limit", async () => {
  const actual = await vi.importActual<typeof import("@/lib/bff-rate-limit")>(
    "@/lib/bff-rate-limit",
  );
  return {
    ...actual,
    checkBffRateLimit: vi.fn(() => ({ allowed: true })),
  };
});

vi.mock("@/lib/embed-ip-rate-limit", () => ({
  checkEmbedIpRateLimit: vi.fn(() => ({ allowed: true })),
  clientIpForEmbedLimit: vi.fn(() => "127.0.0.1"),
  clientIpForRateLimit: vi.fn(() => "127.0.0.1"),
}));

vi.mock("@/lib/adapters/foundry/stream", () => ({
  createFoundryStreamResponse: vi.fn(async () => new Response("foundry", { status: 200 })),
}));

vi.mock("@/lib/adapters/ai-sdk/stream", () => ({
  createAiSdkStreamResponse: vi.fn(async () => new Response("ai-sdk", { status: 200 })),
}));

vi.mock("@/lib/adapters/digithings/stream", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/adapters/digithings/stream")>(
      "@/lib/adapters/digithings/stream",
    );
  return {
    ...actual,
    createDigigraphTraceStreamResponse: vi.fn(
      async () => new Response("trace", { status: 200 }),
    ),
  };
});

vi.mock("@/lib/digigraph-upstream", () => ({
  resolveDigigraphUpstreamAuth: vi.fn(),
  DigigraphUpstreamAuthError: class DigigraphUpstreamAuthError extends Error {},
  DigigraphUpstreamUnavailableError: class DigigraphUpstreamUnavailableError extends Error {},
  DIGIKEY_UNAVAILABLE_RETRY_AFTER_SECONDS: 5,
}));

vi.mock("@/lib/ecosystem", () => ({
  getEcosystemEndpoints: vi.fn(async () => ({
    digigraphUrl: "http://127.0.0.1:8000",
    digiquantUrl: "http://127.0.0.1:8001",
    digitraceUrl: "http://127.0.0.1:8003",
    digisearchUrl: "",
  })),
}));

vi.mock("@/lib/digigraph", () => ({
  createDigiGraphClient: vi.fn(() => () => ({})),
  digigraphModelName: vi.fn(() => "digigraph"),
}));

vi.mock("@/lib/byok-openrouter", () => ({
  normalizeOpenRouterModel: vi.fn((m: string) => m.trim()),
}));

vi.mock("ai", async () => {
  const actual = await vi.importActual<typeof import("ai")>("ai");
  return {
    ...actual,
    convertToModelMessages: vi.fn(async (m: unknown[]) => m),
    streamText: vi.fn(() => ({
      stream: new ReadableStream({ start(c) { c.close(); } }),
    })),
    toUIMessageStream: vi.fn(() => new ReadableStream({ start(c) { c.close(); } })),
    createUIMessageStreamResponse: vi.fn(({ headers }: { headers?: HeadersInit }) =>
      new Response("stream", { status: 200, headers }),
    ),
    smoothStream: vi.fn(() => ({})),
  };
});

import { requireDigiChatAuth } from "@/lib/request-auth";
import { resolveChatTenantContext } from "@/lib/chat-route-context";
import type { EmbedChatTenantContext } from "@/lib/embed-chat-tenant";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import { checkEmbedIpRateLimit, clientIpForRateLimit } from "@/lib/embed-ip-rate-limit";
import { activeGuardrailStore, resetGuardrailStoreForTests } from "@/lib/guardrails/store";
import {
  DigigraphUpstreamAuthError,
  DigigraphUpstreamUnavailableError,
  resolveDigigraphUpstreamAuth,
} from "@/lib/digigraph-upstream";
import { createFoundryStreamResponse } from "@/lib/adapters/foundry/stream";
import { createAiSdkStreamResponse } from "@/lib/adapters/ai-sdk/stream";
import { createDigigraphTraceStreamResponse } from "@/lib/adapters/digithings/stream";
import { resetEmbedTrialQuotaForTests } from "@/lib/embed-turn-quota";
import { resetChatRunLocksForTests } from "@/lib/chat-run-lock";
import { EMBED_FREE_TURN_LIMIT, EMBED_TRIAL_TURN_LIMIT } from "@/lib/embed-turn-limits";
import { streamText, createUIMessageStreamResponse } from "ai";
import { parseDigichatConfig } from "@/lib/deploy-config";
import {
  loadDigichatConfig,
  resetDigichatConfigForTests,
  setDigichatConfigForTests,
} from "@/lib/deploy-config/loader";
import { catalogModelRate } from "@/lib/model-picker-catalog";
import {
  chargePremiumUsage,
  premiumSpendIdentity,
  premiumUserKey,
  resetPremiumSpendForTests,
} from "@/lib/premium-budget/budget";
import { createDigiGraphClient } from "@/lib/digigraph";

function catalogWithSearchVault() {
  return parseDigichatConfig({
    version: 1,
    deployment: {
      slug: "local",
      backend: { type: "digigraph" },
      tools: {
        catalog: [
          { id: "digisearch", default: true },
          { id: "digivault", default: true },
        ],
      },
    },
  });
}

describe("POST /api/chat", () => {
  const env = process.env;

  beforeEach(() => {
    process.env = { ...env, DIGICHAT_TRACE_UI: "0" };
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(resolveChatTenantContext).mockResolvedValue(mockAuthCtx);
    vi.mocked(resolveDigigraphUpstreamAuth).mockResolvedValue({
      bearer: "jwt-token",
      litellmProxyApiKey: null,
    });
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: true });
    vi.mocked(checkEmbedIpRateLimit).mockReturnValue({ allowed: true });
    vi.mocked(clientIpForRateLimit).mockReset();
    vi.mocked(clientIpForRateLimit).mockReturnValue("127.0.0.1");
    resetEmbedTrialQuotaForTests();
    resetChatRunLocksForTests();
    resetPremiumSpendForTests();
vi.mocked(createFoundryStreamResponse).mockClear();
    vi.mocked(createAiSdkStreamResponse).mockClear();
    vi.mocked(createDigigraphTraceStreamResponse).mockClear();
    vi.mocked(createUIMessageStreamResponse).mockImplementation(
      ({ headers }: { headers?: HeadersInit }) =>
        new Response("stream", { status: 200, headers }),
    );
  });

  afterEach(() => {
    process.env = env;
  });

  it("returns 401 when auth and embed context both fail", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    vi.mocked(resolveChatTenantContext).mockResolvedValue(unauthorizedResponse);
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: [{ id: "1", role: "user", parts: [] }] }),
      })
    );
    expect(res.status).toBe(401);
  });

  it("returns 503 license_revoked before auth when the license latch is revoked", async () => {
    const { applyHeartbeatResult, resetLicenseStateForTests } = await import(
      "@/lib/license/state"
    );
    try {
      resetLicenseStateForTests();
      applyHeartbeatResult("denied", "heartbeat_deny_revoked");
      vi.mocked(requireDigiChatAuth).mockClear();
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ messages: [{ id: "1", role: "user", parts: [] }] }),
        })
      );
      expect(res.status).toBe(503);
      expect(await res.json()).toMatchObject({ error: "license_revoked" });
      expect(res.headers.get("retry-after")).toBeNull();
      expect(vi.mocked(requireDigiChatAuth)).not.toHaveBeenCalled();
    } finally {
      resetLicenseStateForTests();
    }
  });

  it("returns 503 when embed gate blocks anonymous embed", async () => {
    vi.mocked(resolveChatTenantContext).mockResolvedValue(
      new Response(JSON.stringify({ error: "embed_disabled" }), { status: 503 })
    );
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://digithings.ai",
        },
        body: JSON.stringify({ messages: [{ id: "1", role: "user", parts: [] }] }),
      })
    );
    expect(res.status).toBe(503);
  });

  it("returns 400 when messages missing", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({}),
      })
    );
    expect(res.status).toBe(400);
  });

  it("answers 503 upstream_unavailable with a Retry-After when digikey is cold", async () => {
    // A cold digikey is a retryable dependency, not a credential problem, so
    // it must not be answered 502 upstream_auth (DIG-4424).
    vi.mocked(resolveDigigraphUpstreamAuth).mockRejectedValue(
      new DigigraphUpstreamUnavailableError(
        "digikey did not answer the bff_session exchange — it is cold or unreachable (last answer: 503). This is not a DIGIKEY_BFF_TOKEN problem; retry in a few seconds."
      )
    );
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(503);
    const body = (await res.json()) as { error: string; message: string };
    expect(body.error).toBe("upstream_unavailable");
    expect(body.message).toContain("not a DIGIKEY_BFF_TOKEN problem");
    expect(res.headers.get("retry-after")).toBe("5");
  });

  it("does not refuse the retry with 409 run_id_replay after a cold digikey", async () => {
    // The client repeats the send with the same X-Digi-Run-Id when it obeys
    // the Retry-After, so a request that failed before it produced a turn must
    // not leave the run id behind and turn that retry into a 409 (DIG-4424).
    vi.mocked(resolveDigigraphUpstreamAuth).mockRejectedValue(
      new DigigraphUpstreamUnavailableError(
        "digikey did not answer the bff_session exchange — it is cold or unreachable (last answer: 503). This is not a DIGIKEY_BFF_TOKEN problem; retry in a few seconds."
      )
    );
    const request = () =>
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digichat-session": "sess-cold",
          "x-digi-run-id": "run-cold-1",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      });

    const first = await POST(request());
    expect(first.status).toBe(503);

    const second = await POST(request());
    expect(second.status).toBe(503);
    const body = (await second.json()) as { error: string };
    expect(body.error).toBe("upstream_unavailable");
  });

  it("still answers 502 upstream_auth when digikey refuses the token", async () => {
    vi.mocked(resolveDigigraphUpstreamAuth).mockRejectedValue(
      new DigigraphUpstreamAuthError(
        "digikey rejected the bff_session exchange (answered 401). Check DIGIKEY_BFF_TOKEN and digikey configuration."
      )
    );
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(502);
    const body = (await res.json()) as { error: string; message: string };
    expect(body.error).toBe("upstream_auth");
    expect(body.message).toContain("DIGIKEY_BFF_TOKEN");
    expect(res.headers.get("retry-after")).toBeNull();
  });

  it("streams response and forwards abortSignal to streamText", async () => {
    const controller = new AbortController();
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
        signal: controller.signal,
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls[0]?.[0] as { abortSignal?: AbortSignal };
    expect(call?.abortSignal).toBeInstanceOf(AbortSignal);
    expect(call?.abortSignal?.aborted).toBe(false);
  });

  it("forwards the full multi-turn messages array to streamText", async () => {
    const messages = [
      { id: "1", role: "user", parts: [{ type: "text", text: "first" }] },
      { id: "2", role: "assistant", parts: [{ type: "text", text: "reply" }] },
      { id: "3", role: "user", parts: [{ type: "text", text: "second" }] },
    ];
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      messages?: unknown[];
    };
    expect(call?.messages).toHaveLength(3);
  });

  it("returns 429 when rate limited", async () => {
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: false, retryAfterSec: 30 });
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: [{ id: "1", role: "user", parts: [] }] }),
      })
    );
    expect(res.status).toBe(429);
  });

  it("returns 429 when the anonymous embed IP limiter blocks", async () => {
    process.env.DIGICHAT_LEGACY_EMBED_ENABLED = "1";
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    vi.mocked(checkBffRateLimit).mockClear();
    vi.mocked(checkEmbedIpRateLimit).mockReturnValue({ allowed: false, retryAfterSec: 45 });
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://digithings.ai",
        },
        body: JSON.stringify({ messages: [{ id: "1", role: "user", parts: [] }] }),
      })
    );
    expect(res.status).toBe(429);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("rate_limit_exceeded");
    // The IP gate short-circuits before the shared embed:anonymous bucket check.
    expect(checkBffRateLimit).not.toHaveBeenCalled();
  });

  it("does not invoke the embed IP limiter for authenticated non-embed requests", async () => {
    vi.mocked(checkEmbedIpRateLimit).mockClear();
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    expect(checkEmbedIpRateLimit).not.toHaveBeenCalled();
  });

  it("routes OpenRouter BYOK through digigraph with BYOK headers", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-byok-key": "sk-or-v1-test",
          "x-byok-provider": "openrouter",
          "x-byok-model": "openai/gpt-4o-mini",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    expect(resolveDigigraphUpstreamAuth).toHaveBeenCalled();
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-BYOK-Key"]).toBe("sk-or-v1-test");
    expect(call?.headers?.["X-BYOK-Provider"]).toBe("openrouter");
    expect(call?.headers?.["X-BYOK-Model"]).toBe("openai/gpt-4o-mini");
  });

  it("runs the first turn on the tenant's curated models.default", async () => {
    setDigichatConfigForTests(
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "local",
          backend: { type: "digigraph" },
          models: {
            default: "deepseek/deepseek-v4.1-flash",
            available: ["deepseek/deepseek-v4.1-flash", "z-ai/glm-5.3-flash"],
            allowPicker: true,
          },
        },
      }),
    );
    try {
      // Force the trace adapter (the live path) so the request body model is observable.
      delete process.env.DIGICHAT_TRACE_UI;
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json", "x-digichat-trace": "1" },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0] as {
        model?: string;
        upstreamHeaders?: Record<string, string>;
      };
      expect(call?.model).toBe("deepseek/deepseek-v4.1-flash");
      expect(call?.upstreamHeaders?.["X-Digi-House-Model"]).toBe("deepseek/deepseek-v4.1-flash");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  function catalogDeployment(costPerWindow?: { usd: number; windowSeconds: number }) {
    return parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "local",
        backend: { type: "digigraph" },
        models: {
          catalog: true,
          ...(costPerWindow ? { costPerWindow } : {}),
        },
      },
    });
  }

  it("falls back to Auto once the premium budget is spent", async () => {
    const budget = { usd: 0.0125565, windowSeconds: 86400 };
    setDigichatConfigForTests(catalogDeployment(budget));
    const session = "sess-premium-spent";
    const rate = catalogModelRate("z-ai/glm-5.3");
    expect(rate).toBeTruthy();
    const key = premiumUserKey(
      mockAuthCtx.tenantSlug,
      premiumSpendIdentity({ userId: mockAuthCtx.ownerUserSub, ip: "127.0.0.1" }),
    );
    const now = Date.now();
    chargePremiumUsage(key, rate!, undefined, now);
    chargePremiumUsage(key, rate!, undefined, now);
    chargePremiumUsage(key, rate!, undefined, now);
    try {
      delete process.env.DIGICHAT_TRACE_UI;
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digichat-trace": "1",
            "x-digichat-session": session,
            "x-digi-model": "z-ai/glm-5.3",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0] as {
        model?: string;
        preface?: string;
        onUsage?: unknown;
        responseHeaders?: Record<string, string>;
        upstreamHeaders?: Record<string, string>;
      };
      expect(call?.responseHeaders?.["X-Digi-Premium-Fallback"]).toBe("auto");
      expect(call?.model).toBe("deepseek/deepseek-v4.1-flash-1017");
      expect(call?.preface).toMatch(/premium budget/);
      expect(call?.onUsage).toBeUndefined();
      expect(call?.upstreamHeaders?.["X-Digi-House-Model"]).toBe(
        "deepseek/deepseek-v4.1-flash-1017",
      );
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("serves a premium OCC model with no budget fallback", async () => {
    setDigichatConfigForTests(
      parseDigichatConfig({
        version: 1,
        hosts: {
          "occ.digithings.ai": {
            slug: "occ",
            backend: { type: "digigraph" },
            models: {
              catalog: true,
              occPicker: true,
              presets: ["auto", "reasoning", "fast", "light"],
              showFullList: true,
            },
          },
        },
      }),
    );
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      tenantSlug: "occ",
      ownerUserSub: "embed:anonymous",
      embedConfig: {
        slug: "occ",
        gateMode: "ungated",
        theme: "light",
        attribution: false,
        token: "tok",
        backend: { type: "digigraph" },
        activityDetail: "labels",
      },
    } as EmbedChatTenantContext);
    try {
      delete process.env.DIGICHAT_TRACE_UI;
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digichat-trace": "1",
            "x-embed-host": "https://occ.digithings.ai",
            "x-digi-model": "z-ai/glm-5.3",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0] as {
        model?: string;
        onUsage?: unknown;
        responseHeaders?: Record<string, string>;
      };
      expect(call?.model).toBe("z-ai/glm-5.3");
      expect(call?.onUsage).toBeUndefined();
      expect(call?.responseHeaders?.["X-Digi-Premium-Fallback"]).toBeUndefined();
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("does not reset the premium window when the session header changes", async () => {
    const budget = { usd: 0.0125565, windowSeconds: 86400 };
    setDigichatConfigForTests(catalogDeployment(budget));
    const rate = catalogModelRate("z-ai/glm-5.3");
    expect(rate).toBeTruthy();
    const key = premiumUserKey(
      mockAuthCtx.tenantSlug,
      premiumSpendIdentity({ userId: mockAuthCtx.ownerUserSub, ip: "127.0.0.1" }),
    );
    const now = Date.now();
    chargePremiumUsage(key, rate!, undefined, now);
    chargePremiumUsage(key, rate!, undefined, now);
    chargePremiumUsage(key, rate!, undefined, now);
    const post = async (session?: string) => {
      const headers: Record<string, string> = {
        "content-type": "application/json",
        "x-digichat-trace": "1",
        "x-digi-model": "z-ai/glm-5.3",
      };
      if (session) headers["x-digichat-session"] = session;
      delete process.env.DIGICHAT_TRACE_UI;
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers,
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0] as {
        model?: string;
        preface?: string;
        responseHeaders?: Record<string, string>;
      };
      expect(call?.model).toBe("deepseek/deepseek-v4.1-flash-1017");
      expect(call?.preface).toMatch(/premium budget/);
      expect(call?.responseHeaders?.["X-Digi-Premium-Fallback"]).toBe("auto");
    };
    try {
      await post("sess-a");
      await post("sess-b");
      await post();
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("keeps rotating x-digichat-peer-ip values on one anonymous premium window", async () => {
    delete process.env.DIGICHAT_PEER_STAMP;
    process.env.DIGICHAT_TRUSTED_PROXIES = "203.0.113.7,198.51.100.8,192.0.2.10";
    const actual = await vi.importActual<typeof import("@/lib/embed-ip-rate-limit")>(
      "@/lib/embed-ip-rate-limit",
    );
    vi.mocked(clientIpForRateLimit).mockImplementation((req: Request) =>
      actual.clientIpForRateLimit(req),
    );
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      tenantSlug: "public",
      ownerUserSub: "embed:anonymous",
    });
    const budget = { usd: 0.0125565, windowSeconds: 86400 };
    setDigichatConfigForTests(catalogDeployment(budget));
    const rate = catalogModelRate("z-ai/glm-5.3");
    expect(rate).toBeTruthy();
    const key = premiumUserKey(
      "public",
      premiumSpendIdentity({ userId: "embed:anonymous", ip: "unknown" }),
    );
    expect(key).toBe("public:anonymous");
    const now = Date.now();
    chargePremiumUsage(key, rate!, undefined, now);
    chargePremiumUsage(key, rate!, undefined, now);
    chargePremiumUsage(key, rate!, undefined, now);
    const peers = ["203.0.113.7", "198.51.100.8", "192.0.2.10"];
    try {
      delete process.env.DIGICHAT_TRACE_UI;
      for (const peer of peers) {
        const res = await POST(
          new Request("http://localhost/api/chat", {
            method: "POST",
            headers: {
              "content-type": "application/json",
              "x-digichat-trace": "1",
              "x-digi-model": "z-ai/glm-5.3",
              "x-digichat-peer-ip": peer,
              "x-forwarded-for": `${peer}, 10.0.0.1`,
              "cf-connecting-ip": peer,
            },
            body: JSON.stringify({
              messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
            }),
          }),
        );
        expect(res.status).toBe(200);
        const call = vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0] as {
          model?: string;
          responseHeaders?: Record<string, string>;
        };
        expect(call?.model).toBe("deepseek/deepseek-v4.1-flash-1017");
        expect(call?.responseHeaders?.["X-Digi-Premium-Fallback"]).toBe("auto");
      }
    } finally {
      delete process.env.DIGICHAT_TRUSTED_PROXIES;
      delete process.env.DIGICHAT_PEER_STAMP;
      resetDigichatConfigForTests();
      vi.mocked(clientIpForRateLimit).mockReset();
      vi.mocked(clientIpForRateLimit).mockReturnValue("127.0.0.1");
      vi.mocked(resolveChatTenantContext).mockResolvedValue(mockAuthCtx);
    }
  });

  it("shows the Auto fallback notice on the non-trace path when no default is set", async () => {
    const budget = { usd: 0.0125565, windowSeconds: 86400 };
    const cfg = catalogDeployment(budget);
    if (cfg.deployment?.models) delete cfg.deployment.models.default;
    setDigichatConfigForTests(cfg);
    const rate = catalogModelRate("z-ai/glm-5.3");
    expect(rate).toBeTruthy();
    const key = premiumUserKey(
      mockAuthCtx.tenantSlug,
      premiumSpendIdentity({ userId: mockAuthCtx.ownerUserSub, ip: "127.0.0.1" }),
    );
    const now = Date.now();
    chargePremiumUsage(key, rate!, undefined, now);
    chargePremiumUsage(key, rate!, undefined, now);
    chargePremiumUsage(key, rate!, undefined, now);
    try {
      process.env.DIGICHAT_TRACE_UI = "0";
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digichat-trace": "0",
            "x-digi-model": "z-ai/glm-5.3",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      expect(res.headers.get("X-Digi-Premium-Fallback")).toBe("auto");
      const sent = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      expect(sent?.headers?.["X-Digi-House-Model"]).toBe("deepseek/deepseek-v4.1-flash-1017");
      const streamArg = vi.mocked(createUIMessageStreamResponse).mock.calls.at(-1)?.[0] as {
        stream: ReadableStream<unknown>;
      };
      const reader = streamArg.stream.getReader();
      const chunks: unknown[] = [];
      for (;;) {
        const next = await reader.read();
        if (next.done) break;
        chunks.push(next.value);
      }
      expect(JSON.stringify(chunks)).toMatch(/premium budget/);
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("keeps a premium pick while the budget still has room", async () => {
    setDigichatConfigForTests(
      catalogDeployment({ usd: 0.0125565, windowSeconds: 86400 }),
    );
    try {
      delete process.env.DIGICHAT_TRACE_UI;
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digichat-trace": "1",
            "x-digichat-session": "sess-premium-open",
            "x-digi-model": "z-ai/glm-5.3",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0] as {
        model?: string;
        preface?: string;
        onUsage?: unknown;
        responseHeaders?: Record<string, string>;
      };
      expect(call?.responseHeaders?.["X-Digi-Premium-Fallback"]).toBeUndefined();
      expect(call?.model).toBe("z-ai/glm-5.3");
      expect(call?.preface).toBeUndefined();
      expect(typeof call?.onUsage).toBe("function");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("does not meter a premium pick when the deployment has no budget", async () => {
    setDigichatConfigForTests(catalogDeployment());
    try {
      delete process.env.DIGICHAT_TRACE_UI;
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digichat-trace": "1",
            "x-digichat-session": "sess-occ",
            "x-digi-model": "google/gemini-3.8-flash",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0] as {
        model?: string;
        preface?: string;
        onUsage?: unknown;
        responseHeaders?: Record<string, string>;
      };
      expect(call?.responseHeaders?.["X-Digi-Premium-Fallback"]).toBeUndefined();
      expect(call?.model).toBe("google/gemini-3.8-flash");
      expect(call?.preface).toBeUndefined();
      expect(call?.onUsage).toBeUndefined();
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("rejects a house X-Digi-Model that is not on the CI picker allowlist", async () => {
    setDigichatConfigForTests(
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "local",
          backend: { type: "digigraph" },
          models: {
            default: "deepseek/deepseek-v4-flash",
            available: ["deepseek/deepseek-v4-flash", "z-ai/glm-5.3-flash"],
            allowPicker: true,
          },
        },
      }),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-model": "openai/gpt-4o-mini",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(400);
      const body = (await res.json()) as { error: string };
      expect(body.error).toBe("model_not_allowed");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("does not apply the house picker allowlist when BYOK is bound", async () => {
    setDigichatConfigForTests(
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "local",
          backend: { type: "digigraph" },
          models: {
            default: "deepseek/deepseek-v4-flash",
            available: ["deepseek/deepseek-v4-flash"],
            allowPicker: true,
          },
        },
      }),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-model": "gpt-4o-mini",
            "x-byok-key": "sk-test",
            "x-byok-provider": "openai",
            "x-byok-model": "gpt-4o-mini",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("forwards OCC corpus headers from digigraph embed backend config", async () => {
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      tenantSlug: "occ",
      ownerUserSub: "embed:anonymous",
      embedConfig: {
        slug: "occ",
        gateMode: "ungated",
        theme: "dark",
        attribution: false,
        token: "tok",
        backend: {
          type: "digigraph",
          digisearchIndex: "occ_help",
          vaultPathPrefix: "clients/online-compliance-center",
        },
        activityDetail: "full",
      },
    } as EmbedChatTenantContext);
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://occ.digithings.ai",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "policy?" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-Digi-Tenant"]).toBe("occ");
    expect(call?.headers?.["X-Digi-Corpus-Index"]).toBe("occ_help");
    expect(call?.headers?.["X-Digi-Vault-Prefix"]).toBe(
      "clients/online-compliance-center"
    );
  });

  it("forwards X-Digi-Language to digigraph upstream headers", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digi-language": "de",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-Digi-Language"]).toBe("de");
  });

  it("omits X-Digi-Language from upstream headers when the request sends English", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digi-language": "en",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-Digi-Language"]).toBeUndefined();
  });

  it("forwards X-Digi-Search-Engine to digigraph upstream headers", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digi-search-engine": "exa",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "news" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-Digi-Search-Engine"]).toBe("exa");
  });

  it("drops X-Digi-Search-Engine for unknown, blank, or auto engines", async () => {
    for (const engine of ["not-an-engine", "", "   ", "auto", "AUTO"]) {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-search-engine": engine,
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "news" }] }],
          }),
        })
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      expect(call?.headers?.["X-Digi-Search-Engine"]).toBeUndefined();
    }
  });

  it("forwards tenant default search engine when browser sends none", async () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "test",
        backend: { type: "digigraph" },
        gate: { searchEngine: "tavily" },
      },
    });
    setDigichatConfigForTests(cfg);
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "news" }] }],
          }),
        })
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      expect(call?.headers?.["X-Digi-Search-Engine"]).toBe("tavily");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("browser search engine beats tenant default", async () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "test",
        backend: { type: "digigraph" },
        gate: { searchEngine: "tavily" },
      },
    });
    setDigichatConfigForTests(cfg);
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-search-engine": "exa",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "news" }] }],
          }),
        })
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      expect(call?.headers?.["X-Digi-Search-Engine"]).toBe("exa");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("explicit browser auto beats tenant default via omission", async () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "test",
        backend: { type: "digigraph" },
        gate: { searchEngine: "tavily" },
      },
    });
    setDigichatConfigForTests(cfg);
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-search-engine": "auto",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "news" }] }],
          }),
        })
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      expect(call?.headers?.["X-Digi-Search-Engine"]).toBeUndefined();
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("forwards X-Digi-Force-Tool to digigraph upstream headers", async () => {
    setDigichatConfigForTests(catalogWithSearchVault());
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-force-tool": "digisearch",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "RS256" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      expect(call?.headers?.["X-Digi-Force-Tool"]).toBe("digisearch");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("forwards X-Digi-Enable-Web-Search only when DIGICHAT_WEB_SEARCH=1 (#3420)", async () => {
    process.env.DIGICHAT_WEB_SEARCH = "1";
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digi-enable-web-search": "1",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "news" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-Digi-Enable-Web-Search"]).toBe("1");
  });

  it("does not forward web search when env gate is off (#3420)", async () => {
    delete process.env.DIGICHAT_WEB_SEARCH;
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digi-enable-web-search": "1",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "news" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-Digi-Enable-Web-Search"]).toBeUndefined();
  });

  it("forwards web search for first-party (null embedConfig) when DIGICHAT_WEB_SEARCH=1", async () => {
    process.env.DIGICHAT_WEB_SEARCH = "1";
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      ...mockAuthCtx,
      embedConfig: null,
    } as EmbedChatTenantContext);
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digi-enable-web-search": "1",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "news" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-Digi-Enable-Web-Search"]).toBe("1");
  });

  it("does not forward web search for first-party (null embedConfig) when env is unset", async () => {
    delete process.env.DIGICHAT_WEB_SEARCH;
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      ...mockAuthCtx,
      embedConfig: null,
    } as EmbedChatTenantContext);
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digi-enable-web-search": "1",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "news" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-Digi-Enable-Web-Search"]).toBeUndefined();
  });

  it("forwards X-Digi-License when the container holds a license (spec §7.1)", async () => {
    const { generateTestKeypair, mintLicenseJwt } = await import(
      "@/lib/license/jwt-fixtures"
    );
    const state = await import("@/lib/license/state");
    try {
      const { publicKeyPem, privateKeyPem } = generateTestKeypair();
      const token = mintLicenseJwt(privateKeyPem);
      process.env.DIGICHAT_LICENSE_JWT = token;
      process.env.DIGIKEY_PUBLIC_KEY_PEM = publicKeyPem;
      state.initLicenseStateAtStartup();
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        })
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      expect(call?.headers?.["X-Digi-License"]).toBe(token);
    } finally {
      state.resetLicenseStateForTests();
      delete process.env.DIGICHAT_LICENSE_JWT;
      delete process.env.DIGIKEY_PUBLIC_KEY_PEM;
    }
  });

  it("omits X-Digi-License when unlicensed (spec §7.1)", async () => {
    const state = await import("@/lib/license/state");
    try {
      state.resetLicenseStateForTests();
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        })
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      expect(call?.headers?.["X-Digi-License"]).toBeUndefined();
    } finally {
      state.resetLicenseStateForTests();
    }
  });

  it("ignores X-Digi-Force-Tool on regenerate (send-only)", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digi-force-tool": "digisearch",
          "x-digi-turn-mode": "regenerate",
          "x-digichat-session": "sess-force-regen",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "RS256" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    await res.text();
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-Digi-Force-Tool"]).toBeUndefined();
  });

  it("drops X-Digi-Force-Tool / X-Digi-Disabled-Tools when catalog is empty (#3806)", async () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "test",
        backend: { type: "digigraph" },
        tools: { catalog: [] },
      },
    });
    setDigichatConfigForTests(cfg);
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-force-tool": "digisearch",
            "x-digi-disabled-tools": "digisearch,digivault",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        })
      );
      expect(res.status).toBe(200);
      await res.text();
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      expect(call?.headers?.["X-Digi-Force-Tool"]).toBeUndefined();
      expect(call?.headers?.["X-Digi-Disabled-Tools"]).toBeUndefined();
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("forwards allowlisted X-Digi-Disabled-Tools and drops unknown tokens (#3733)", async () => {
    setDigichatConfigForTests(catalogWithSearchVault());
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-disabled-tools": "digisearch,rm -rf",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      const forwarded = call?.headers?.["X-Digi-Disabled-Tools"];
      expect(forwarded).toBe("digisearch");
      // Catalog ids forward as-is (#3807) — digigraph expands them upstream.
      expect(forwarded).not.toContain("digisearch_fetch_all");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("forwards X-Digi-Disabled-Tools on regenerate (session prefs, not send-only)", async () => {
    setDigichatConfigForTests(catalogWithSearchVault());
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-disabled-tools": "digivault",
            "x-digi-force-tool": "digisearch",
            "x-digi-turn-mode": "regenerate",
            "x-digichat-session": "sess-disabled-regen",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      await res.text();
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      expect(call?.headers?.["X-Digi-Force-Tool"]).toBeUndefined();
      expect(call?.headers?.["X-Digi-Disabled-Tools"]).toBe("digivault");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("forwards operator MCP YAML and ignores client-supplied X-Digi-Mcp-Servers (#3736)", async () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "datatap",
        backend: { type: "digigraph" },
        mcp: {
          servers: [{ id: "datatap", url: "https://mcp.datatap.example/mcp" }],
        },
      },
    });
    setDigichatConfigForTests(cfg);
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-mcp-servers": '[{"id":"evil","url":"https://evil.example/mcp"}]',
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      const forwarded = call?.headers?.["X-Digi-Mcp-Servers"];
      expect(forwarded).toContain("mcp.datatap.example");
      expect(forwarded).toContain("datatap");
      expect(forwarded).not.toContain("evil");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("merges allowlisted session overlay and ignores operator URL override (#3736)", async () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "datatap",
        backend: { type: "digigraph" },
        mcp: {
          allowUserServers: true,
          servers: [{ id: "datatap", url: "https://mcp.datatap.example/mcp" }],
        },
      },
    });
    setDigichatConfigForTests(cfg);
    try {
      const overlay = JSON.stringify([
        { id: "datatap", url: "https://evil.example/mcp", token: "tok" },
        { id: "linear", url: "https://mcp.linear.app/mcp", auth: "oauth" },
        { id: "loop", url: "http://127.0.0.1:8080/mcp" },
      ]);
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-digi-mcp-session": overlay,
            "x-digi-mcp-servers": '[{"id":"evil","url":"https://evil.example/mcp"}]',
            "x-digi-effort": "high",
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        headers?: Record<string, string>;
      };
      const forwarded = call?.headers?.["X-Digi-Mcp-Servers"] ?? "";
      expect(forwarded).toContain("mcp.datatap.example");
      expect(forwarded).toContain("tok");
      expect(forwarded).toContain("mcp.linear.app");
      expect(forwarded).not.toContain("evil.example");
      expect(forwarded).not.toContain("127.0.0.1");
      expect(call?.headers?.["X-Digi-Effort"]).toBe("high");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("returns 409 run_in_progress for concurrent regen on the same session", async () => {
    vi.mocked(createUIMessageStreamResponse).mockImplementationOnce(
      ({ headers }: { headers?: HeadersInit }) =>
        new Response(
          new ReadableStream({
            start() {
              /* hold open until cancelled */
            },
          }),
          { status: 200, headers },
        ),
    );

    const first = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digichat-session": "sess-concurrent",
          "x-digi-turn-mode": "regenerate",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      }),
    );
    expect(first.status).toBe(200);

    const second = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digichat-session": "sess-concurrent",
          "x-digi-turn-mode": "regenerate",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      }),
    );
    expect(second.status).toBe(409);
    const body = (await second.json()) as { error: string };
    expect(body.error).toBe("run_in_progress");
    await first.body?.cancel();
  });

  it("returns 409 run_id_replay for a duplicate X-Digi-Run-Id", async () => {
    const first = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digichat-session": "sess-runid",
          "x-digi-run-id": "run-dup-1",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      }),
    );
    expect(first.status).toBe(200);
    await first.text();

    const second = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-digichat-session": "sess-runid",
          "x-digi-run-id": "run-dup-1",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      }),
    );
    expect(second.status).toBe(409);
    const body = (await second.json()) as { error: string };
    expect(body.error).toBe("run_id_replay");
  });

  it("passes turnMode to the Foundry adapter", async () => {
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      tenantSlug: "foundry-tenant",
      ownerUserSub: "embed:anonymous",
      embedConfig: {
        slug: "foundry-tenant",
        gateMode: "ungated",
        theme: "light",
        attribution: false,
        token: "tok",
        backend: { type: "foundry", projectEndpoint: "https://x/", agentName: "a" },
        activityDetail: "full",
      },
    } as EmbedChatTenantContext);
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://foundry-tenant.digithings.ai",
          "x-digi-turn-mode": "regenerate",
          "x-external-conversation": "conv_1",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      }),
    );
    expect(res.status).toBe(200);
    await res.text();
    const call = vi.mocked(createFoundryStreamResponse).mock.calls.at(-1)?.[0] as {
      turnMode?: string;
    };
    expect(call?.turnMode).toBe("regenerate");
  });

  it("passes responseLanguage to the Foundry adapter", async () => {
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      tenantSlug: "foundry-tenant",
      ownerUserSub: "embed:anonymous",
      embedConfig: {
        slug: "foundry-tenant",
        gateMode: "ungated",
        theme: "light",
        attribution: false,
        token: "tok",
        backend: { type: "foundry", projectEndpoint: "https://x/", agentName: "a" },
        activityDetail: "full",
      },
    } as EmbedChatTenantContext);
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://foundry-tenant.digithings.ai",
          "x-digi-language": "fr",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(createFoundryStreamResponse).mock.calls.at(-1)?.[0] as {
      responseLanguage?: string;
    };
    expect(call?.responseLanguage).toBe("fr");
  });

  it("passes maxToolCalls from the foundry backend to the adapter", async () => {
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      tenantSlug: "foundry-tenant",
      ownerUserSub: "embed:anonymous",
      embedConfig: {
        slug: "foundry-tenant",
        gateMode: "ungated",
        theme: "light",
        attribution: false,
        token: "tok",
        backend: {
          type: "foundry",
          projectEndpoint: "https://x/",
          agentName: "fixture-agent",
          maxToolCalls: 5,
        },
        activityDetail: "full",
      },
    } as EmbedChatTenantContext);
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://foundry-tenant.digithings.ai",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      }),
    );
    expect(res.status).toBe(200);
    await res.text();
    const call = vi.mocked(createFoundryStreamResponse).mock.calls.at(-1)?.[0] as {
      maxToolCalls?: number;
    };
    expect(call?.maxToolCalls).toBe(5);
    expect(call && "guard" in call).toBe(true);
  });

  it.each([
    ["high", "high"],
    ["LOW", "low"],
    ["max", undefined],
    [undefined, undefined],
  ])("passes /effort %s to the foundry adapter as %s", async (header, expected) => {
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      tenantSlug: "foundry-tenant",
      ownerUserSub: "embed:anonymous",
      embedConfig: {
        slug: "foundry-tenant",
        gateMode: "ungated",
        theme: "light",
        attribution: false,
        token: "tok",
        backend: { type: "foundry", projectEndpoint: "https://x/", agentName: "fixture-agent" },
        activityDetail: "full",
      },
    } as EmbedChatTenantContext);
    const headers: Record<string, string> = {
      "content-type": "application/json",
      "x-embed-host": "https://foundry-tenant.digithings.ai",
    };
    if (header) headers["x-digi-effort"] = header;
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers,
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      }),
    );
    expect(res.status).toBe(200);
    await res.text();
    const call = vi.mocked(createFoundryStreamResponse).mock.calls.at(-1)?.[0] as {
      reasoningEffort?: string;
    };
    expect(call?.reasoningEffort).toBe(expected);
  });

  it("prefers guardrails.maxToolCallsPerTurn over the Foundry alias", async () => {
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      tenantSlug: "foundry-tenant",
      ownerUserSub: "embed:anonymous",
      embedConfig: {
        slug: "foundry-tenant",
        gateMode: "ungated",
        theme: "light",
        attribution: false,
        token: "tok",
        backend: {
          type: "foundry",
          projectEndpoint: "https://x/",
          agentName: "fixture-agent",
          maxToolCalls: 9,
        },
        guardrails: { maxToolCallsPerTurn: 4 },
        activityDetail: "full",
      },
    } as EmbedChatTenantContext);
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://foundry-tenant.digithings.ai",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      }),
    );
    expect(res.status).toBe(200);
    await res.text();
    const call = vi.mocked(createFoundryStreamResponse).mock.calls.at(-1)?.[0] as {
      maxToolCalls?: number;
      guard?: { toolCap?: number; active?: boolean };
    };
    expect(call?.maxToolCalls).toBe(4);
    expect(call?.guard?.active).toBe(true);
    expect(call?.guard?.toolCap).toBe(4);
  });

  it("keys anonymous token spend by the server-derived IP, not the client session", async () => {
    vi.mocked(clientIpForRateLimit).mockReturnValue("203.0.113.9");
    resetGuardrailStoreForTests();
    const session = "client-chosen-session";
    vi.mocked(resolveChatTenantContext).mockResolvedValue({
      tenantSlug: "public",
      ownerUserSub: "embed:anonymous",
      embedConfig: {
        slug: "public",
        gateMode: "ungated",
        theme: "light",
        attribution: false,
        token: "tok",
        backend: {
          type: "foundry",
          projectEndpoint: "https://x/",
          agentName: "fixture-agent",
        },
        guardrails: { tokensPerMinute: { user: 80_000 } },
        activityDetail: "full",
      },
    } as EmbedChatTenantContext);
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-embed-host": "https://public.digithings.ai",
            "x-digichat-session": session,
          },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(createFoundryStreamResponse).mock.calls.at(-1)?.[0] as {
        guard?: { recordUsage: (usage: { totalTokens: number }) => void };
      };
      call?.guard?.recordUsage({ totalTokens: 10 });
      const spent = (key: string) =>
        activeGuardrailStore()
          .read(key, Date.now())
          .events.reduce((sum, event) => sum + event.tokens, 0);
      expect(spent("tpm:user:public:203.0.113.9")).toBe(10);
      expect(spent(`tpm:user:public:${session}`)).toBe(0);
      expect(spent("tpm:user:public:anonymous")).toBe(0);
    } finally {
      resetGuardrailStoreForTests();
      vi.mocked(clientIpForRateLimit).mockReturnValue("127.0.0.1");
    }
  });

  it("stops tools from the trace-off stream when the guard says the cap is spent", async () => {
    setDigichatConfigForTests(
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "local",
          backend: { type: "digigraph" },
          guardrails: { maxToolCallsPerTurn: 1 },
        },
      }),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
          }),
        }),
      );
      expect(res.status).toBe(200);
      const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
        prepareStep?: (step: {
          steps: { toolCalls?: unknown[] }[];
          messages: { role: string; content: unknown }[];
        }) => Promise<{ toolChoice?: string } | undefined>;
      };
      const prepared = await call.prepareStep?.({
        steps: [{ toolCalls: [{}] }],
        messages: [{ role: "user", content: "hi" }],
      });
      expect(prepared?.toolChoice).toBe("none");
    } finally {
      resetDigichatConfigForTests();
    }
  });

  it("returns 400 when OpenRouter BYOK missing model", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-byok-key": "sk-or-v1-test",
          "x-byok-provider": "openrouter",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBe("byok_model_required");
  });

  // #5029: the hint used to spell one provider's model out in full
  // ("openai/gpt-4o-mini") while eliding the others as "claude-…" / "gemini/…".
  // A model id is provider vocabulary, not a stable part of this contract, so
  // every example is elided the same way. Reverting the message to name a
  // concrete slug fails on the last assertion.
  // #5029: this message used to name three hardcoded model ids in one sentence
  // sent to every provider, so two of the three were not served by the provider
  // being told to use them. The example now comes from the caller's own provider
  // entry in config/byok-providers.json — the same catalog digigraph's
  // byok_model_example() reads, so the two refusals cannot drift apart.
  it("names a model the caller's own provider serves (#5029)", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-byok-key": "sk-or-v1-test",
          "x-byok-provider": "openrouter",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    // openrouter's own first fallbackModels entry — not openai's, even though
    // openrouter happens to route to it.
    expect(body.message).toContain("openai/gpt-4o-mini");
    // No other provider's examples leak into an openrouter caller's message.
    expect(body.message).not.toContain("claude-");
    expect(body.message).not.toContain("gemini-");
  });

  it("does not offer an OpenAI model to a non-OpenAI provider (#5029)", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-byok-key": "xai-test",
          "x-byok-provider": "xai",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.message).toMatch(/grok-/);
    expect(body.message).not.toContain("gpt-");
  });

  // #2351: byokNeedsModel is now byokRequiresModel(byokProvider) from the shared
  // apps/digichat/src/lib/byok-providers.ts module instead of a hand-written
  // OR-chain — these three cover the other requiresModel:true providers the old
  // OR-chain also happened to list (anthropic/gemini/xai), proving the swap kept
  // every one of them gated exactly as before.
  it("returns 400 when Anthropic BYOK missing model", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-byok-key": "sk-ant-test",
          "x-byok-provider": "anthropic",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBe("byok_model_required");
  });

  it("returns 400 when Gemini BYOK missing model", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-byok-key": "AIza-test",
          "x-byok-provider": "gemini",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBe("byok_model_required");
  });

  it("returns 400 when x.ai BYOK missing model", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-byok-key": "xai-test",
          "x-byok-provider": "xai",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBe("byok_model_required");
  });

  // The BFF used to forward X-BYOK-Model only when byokRequiresModel(provider)
  // was true, so a caller who *did* name a model for OpenAI had it stripped
  // here and digigraph answered on the deployment's own default — billed to the
  // operator while the caller's key sat bound and unspent (#2490). Requiring a
  // model and forwarding one the caller sent are different questions.
  it("forwards X-BYOK-Model for a provider that does not require one", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-byok-key": "sk-test",
          "x-byok-provider": "openai",
          "x-byok-model": "gpt-4o-mini",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-BYOK-Model"]).toBe("gpt-4o-mini");
  });

  // OpenAI is the one requiresModel:false provider today — byokRequiresModel
  // must still exempt it after the OR-chain → shared-predicate swap (#2351).
  it("does not require a model for OpenAI BYOK (byokRequiresModel exemption)", async () => {
    const res = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-byok-key": "sk-test",
          "x-byok-provider": "openai",
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-BYOK-Key"]).toBe("sk-test");
    expect(call?.headers?.["X-BYOK-Provider"]).toBe("openai");
    expect(call?.headers?.["X-BYOK-Model"]).toBeUndefined();
  });

  describe("trial_form gate", () => {
    const trialCtx = {
      tenantSlug: "datatap",
      ownerUserSub: "embed:anonymous",
      embedConfig: {
        slug: "datatap",
        gateMode: "trial_form",
        theme: "light",
        attribution: false,
        token: "tok",
        backend: { type: "foundry", projectEndpoint: "https://x/", agentName: "a" },
        activityDetail: "labels",
      },
    };

    function trialReq(headers: Record<string, string> = {}): Request {
      return new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json", "x-embed-host": "https://datatap.stream", ...headers },
        body: JSON.stringify({ messages: [{ role: "user", parts: [{ type: "text", text: "hi" }] }] }),
      });
    }

    beforeEach(() => {
      vi.mocked(resolveChatTenantContext).mockResolvedValue(trialCtx as never);
    });

    describe("when the tenant quota service cannot answer", () => {
      const CONSUME_URL = "https://quota.test/consume";

      // The tenant configures a consume URL and the client presents a chat token, so
      // the server-side quota replaces the per-IP budget entirely.
      const degradedCtx = {
        ...trialCtx,
        embedConfig: {
          ...trialCtx.embedConfig,
          gate: { consumeUrl: CONSUME_URL },
        },
      };

      beforeEach(() => {
        vi.mocked(resolveChatTenantContext).mockResolvedValue(degradedCtx as never);
      });

      afterEach(() => {
        vi.unstubAllGlobals();
      });

      /**
       * Drive the degraded path for one client IP: every turn is admitted and
       * counted, and the turn after the trial cap is refused with the 402
       * trial_gate.
       */
      async function degradedRun(
        ip: string,
        headers: Record<string, string>,
        provider: () => Promise<Response>,
      ) {
        const { clientIpForEmbedLimit } = await import("@/lib/embed-ip-rate-limit");
        const ipSpy = vi.mocked(clientIpForEmbedLimit).mockReturnValue(ip);
        const fetchMock = vi.fn(async () => provider());
        vi.stubGlobal("fetch", fetchMock);
        const foundryBefore = vi.mocked(createFoundryStreamResponse).mock.calls.length;
        try {
          for (let i = 0; i < EMBED_TRIAL_TURN_LIMIT; i++) {
            const res = await POST(trialReq({ "x-embed-chat-token": "tok", ...headers }));
            expect(res.status).toBe(200);
          }
          const gated = await POST(trialReq({ "x-embed-chat-token": "tok", ...headers }));
          // A non-JSON body must not throw here: the status assertion is the
          // load-bearing one, and a parse error would mask it.
          const body = (await gated.json().catch(() => ({}))) as { error?: string };
          return {
            status: gated.status,
            body,
            providerCalls: fetchMock.mock.calls.length,
            consumeUrl: fetchMock.mock.calls[0]?.[0],
            foundryCalls: vi.mocked(createFoundryStreamResponse).mock.calls.length - foundryBefore,
          };
        } finally {
          ipSpy.mockReturnValue("127.0.0.1");
          vi.unstubAllGlobals();
        }
      }

      it("admits and counts the visitor, and caps the degraded entitlement at the trial budget when the quota service answers 500", async () => {
        const withoutHeader = await degradedRun("10.0.0.1", {}, async () =>
          new Response("boom", { status: 500 }),
        );
        const withHeader = await degradedRun(
          "10.0.0.2",
          { "x-embed-trial-unlock": "1" },
          async () => new Response("boom", { status: 500 }),
        );

        // The provider was actually consulted, on the tenant's consume URL.
        expect(withoutHeader.providerCalls).toBe(EMBED_TRIAL_TURN_LIMIT + 1);
        expect(withHeader.providerCalls).toBe(EMBED_TRIAL_TURN_LIMIT + 1);
        expect(withoutHeader.consumeUrl).toBe(CONSUME_URL);
        expect(withHeader.consumeUrl).toBe(CONSUME_URL);
        // Every admitted turn reached the backend, so the visitor was not just
        // counted but actually served.
        expect(withoutHeader.foundryCalls).toBe(EMBED_TRIAL_TURN_LIMIT);
        expect(withHeader.foundryCalls).toBe(EMBED_TRIAL_TURN_LIMIT);
        // The cap is the trial budget, not the free-3 and not unbounded.
        expect(withoutHeader.status).toBe(402);
        expect(withHeader.status).toBe(402);
        expect(withoutHeader.body.error).toBe("trial_gate");
        expect(withHeader.body.error).toBe("trial_gate");
        // Identical with and without the client-asserted unlock header.
        expect(withHeader.status).toBe(withoutHeader.status);
        expect(withHeader.body).toEqual(withoutHeader.body);
      });

      it("admits and counts the visitor, and caps the degraded entitlement at the trial budget when the quota service request throws", async () => {
        const withoutHeader = await degradedRun("10.0.0.3", {}, async () => {
          throw new Error("network down");
        });
        const withHeader = await degradedRun(
          "10.0.0.4",
          { "x-embed-trial-unlock": "1" },
          async () => {
            throw new Error("network down");
          },
        );

        expect(withoutHeader.providerCalls).toBe(EMBED_TRIAL_TURN_LIMIT + 1);
        expect(withHeader.providerCalls).toBe(EMBED_TRIAL_TURN_LIMIT + 1);
        expect(withoutHeader.consumeUrl).toBe(CONSUME_URL);
        expect(withHeader.consumeUrl).toBe(CONSUME_URL);
        expect(withoutHeader.foundryCalls).toBe(EMBED_TRIAL_TURN_LIMIT);
        expect(withHeader.foundryCalls).toBe(EMBED_TRIAL_TURN_LIMIT);
        expect(withoutHeader.status).toBe(402);
        expect(withHeader.status).toBe(402);
        expect(withoutHeader.body.error).toBe("trial_gate");
        expect(withHeader.body.error).toBe("trial_gate");
        expect(withHeader.status).toBe(withoutHeader.status);
        expect(withHeader.body).toEqual(withoutHeader.body);
      });

      it("admits an uncounted visitor when the client IP cannot be resolved: the bound does not reach them", async () => {
        // Residual, stated here so it is not silently inherited: the degraded raise
        // lives inside the existing `ip !== "unknown"` guard, so a visitor whose IP
        // cannot be resolved skips the per-IP quota entirely — admitted, uncounted,
        // and not bounded by the 100-turn cap. This is pre-existing behaviour of the
        // per-IP quota, unchanged by this leaf; the degraded path does not widen it.
        const { clientIpForEmbedLimit } = await import("@/lib/embed-ip-rate-limit");
        const ipSpy = vi.mocked(clientIpForEmbedLimit).mockReturnValue("unknown");
        const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
        const fetchMock = vi.fn(async () => new Response("boom", { status: 500 }));
        vi.stubGlobal("fetch", fetchMock);
        const turns = EMBED_TRIAL_TURN_LIMIT + 5;
        try {
          for (let i = 0; i < turns; i++) {
            const res = await POST(trialReq({ "x-embed-chat-token": "tok" }));
            expect(res.status).toBe(200);
          }
          // The provider was consulted on every turn: this is the degraded path
          // under test, not a path that skipped the quota service.
          expect(fetchMock.mock.calls.length).toBe(turns);
          // The degraded path was taken and logged, so this case is not vacuous:
          // it is the unavailable verdict that produced the admission, not an
          // "allow" verdict from the provider.
          expect(warnSpy).toHaveBeenCalledWith(
            "[trial-gate] tenant quota service unavailable, bounding the entitlement to the trial cap:",
          );
        } finally {
          warnSpy.mockRestore();
          ipSpy.mockReturnValue("127.0.0.1");
          vi.unstubAllGlobals();
        }
      });
    });

    it(`allows the first ${EMBED_FREE_TURN_LIMIT} turns (server cap) then returns 402 trial_gate without calling Foundry`, async () => {
      // The server-side cap is deliberately looser than the client-advertised
      // free-3 (EMBED_FREE_TURN_LIMIT, see embed-turn-limits.ts) — it's
      // a backstop against localStorage/incognito bypass, not the primary
      // enforcement, so this exercises the route with that cap.
      for (let i = 0; i < EMBED_FREE_TURN_LIMIT; i++) {
        const ok = await POST(trialReq());
        expect(ok.status).toBe(200);
      }
      const gated = await POST(trialReq());
      expect(gated.status).toBe(402);
      expect(gated.headers.get("content-type")).toBe("application/json");
      expect(await gated.json()).toMatchObject({ error: "trial_gate" });
      // Foundry called once per allowed turn, never on the gated turn.
      expect(createFoundryStreamResponse).toHaveBeenCalledTimes(EMBED_FREE_TURN_LIMIT);
    });

    it("honors X-Embed-Trial-Unlock to allow turns past the free limit", async () => {
      for (let i = 0; i < EMBED_FREE_TURN_LIMIT; i++) await POST(trialReq());
      const unlocked = await POST(trialReq({ "x-embed-trial-unlock": "1" }));
      expect(unlocked.status).toBe(200);
      expect(createFoundryStreamResponse).toHaveBeenCalledTimes(EMBED_FREE_TURN_LIMIT + 1);
    });

    it("fails open when the quota check throws, so the turn still reaches the backend", async () => {
      const quotaModule = await import("@/lib/embed-turn-quota");
      const spy = vi
        .spyOn(quotaModule, "isOverEmbedTrialLimit")
        .mockImplementation(() => {
          throw new Error("boom");
        });
      try {
        const res = await POST(trialReq());
        expect(res.status).toBe(200);
        expect(createFoundryStreamResponse).toHaveBeenCalledTimes(1);
      } finally {
        spy.mockRestore();
      }
    });

    // DIG-613: an internal monitor had no sanctioned way past the free-turn cap,
    // so the hourly DataTap answer-integrity check spent the whole 3-turn budget
    // in its first hour and then reported 402 trial_gate on every run after.
    describe("monitor allowlist", () => {
      const MONITOR_SECRET = "monitor-secret-0123456789abcdef0123456789abcdef";

      it("serves an allowlisted monitor indefinitely and never consults the per-IP quota", async () => {
        process.env.DIGICHAT_MONITOR_TOKENS = MONITOR_SECRET;
        const quotaModule = await import("@/lib/embed-turn-quota");
        const overSpy = vi.spyOn(quotaModule, "isOverEmbedTrialLimit");
        const recordSpy = vi.spyOn(quotaModule, "recordEmbedTrialTurn");
        try {
          // Well past the cap, which is the whole point: an hourly job must not
          // be gated after the first three probes.
          for (let i = 0; i < EMBED_FREE_TURN_LIMIT + 3; i++) {
            const res = await POST(
              trialReq({ "x-embed-monitor-token": MONITOR_SECRET }),
            );
            expect(res.status).toBe(200);
          }
          expect(overSpy).not.toHaveBeenCalled();
          expect(recordSpy).not.toHaveBeenCalled();
          expect(createFoundryStreamResponse).toHaveBeenCalledTimes(
            EMBED_FREE_TURN_LIMIT + 3,
          );
        } finally {
          overSpy.mockRestore();
          recordSpy.mockRestore();
        }
      });

      it("still gates a caller holding only the published X-Embed-Token, even with an allowlist configured", async () => {
        // The tenant token is a Stripe-style publishable key rendered into the
        // embedding page (DIG-619), so a bypass keyed on it would be public and
        // would hand every visitor an unlimited budget. This pins that.
        process.env.DIGICHAT_MONITOR_TOKENS = MONITOR_SECRET;
        for (let i = 0; i < EMBED_FREE_TURN_LIMIT; i++) {
          expect((await POST(trialReq({ "x-embed-token": "published-token" }))).status).toBe(200);
        }
        const gated = await POST(trialReq({ "x-embed-token": "published-token" }));
        expect(gated.status).toBe(402);
        expect(await gated.json()).toMatchObject({ error: "trial_gate" });
      });

      it("still gates a caller presenting the wrong monitor secret", async () => {
        process.env.DIGICHAT_MONITOR_TOKENS = MONITOR_SECRET;
        for (let i = 0; i < EMBED_FREE_TURN_LIMIT; i++) {
          await POST(trialReq({ "x-embed-monitor-token": "not-the-secret" }));
        }
        const gated = await POST(trialReq({ "x-embed-monitor-token": "not-the-secret" }));
        expect(gated.status).toBe(402);
        expect(await gated.json()).toMatchObject({ error: "trial_gate" });
      });

      it("fails open when DIGICHAT_MONITOR_TOKENS is absent, leaving the per-IP cap in force for everyone", async () => {
        delete process.env.DIGICHAT_MONITOR_TOKENS;
        for (let i = 0; i < EMBED_FREE_TURN_LIMIT; i++) {
          expect((await POST(trialReq({ "x-embed-monitor-token": MONITOR_SECRET }))).status).toBe(200);
        }
        const gated = await POST(trialReq({ "x-embed-monitor-token": MONITOR_SECRET }));
        expect(gated.status).toBe(402);
        expect(await gated.json()).toMatchObject({ error: "trial_gate" });
      });
    });

    it("skips the quota entirely when the client IP is unknown, so a broken ingress fails open rather than collapsing every visitor into one bucket", async () => {
      const { clientIpForEmbedLimit } = await import("@/lib/embed-ip-rate-limit");
      const spy = vi.mocked(clientIpForEmbedLimit).mockReturnValue("unknown");
      try {
        // Even well past the server cap, every "unknown"-IP request succeeds —
        // the quota is never consulted for a non-identity IP (route.ts).
        for (let i = 0; i < EMBED_FREE_TURN_LIMIT + 2; i++) {
          const res = await POST(trialReq());
          expect(res.status).toBe(200);
        }
      } finally {
        spy.mockReturnValue("127.0.0.1");
      }
    });
  });

  describe("digiquant.io dashboard tenant (#3662)", () => {
    // Canonical dashboard shape: ungated + operator, no gate.consumeUrl, requiredPlanTier desk —
    // Desk+ chat is never capped at free-3, and the trial quota is never consulted.
    // Anonymous embed without a valid plan_tier must get 403.
    const dashboardCtx = {
      tenantSlug: "digiquant-dashboard",
      ownerUserSub: "embed:anonymous",
      embedConfig: {
        slug: "digiquant-dashboard",
        gateMode: "ungated",
        theme: "dark",
        attribution: false,
        token: "dash-secret",
        backend: { type: "digigraph" },
        activityDetail: "full",
        llmAccess: "operator",
        showByok: true,
        requiredPlanTier: "desk",
      },
    };

    const PLAN_PROOF_SECRET = "test-secret-for-plan-proof-3662";

    function dashboardReq(headers: Record<string, string> = {}): Request {
      return new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://digiquant.io",
          ...headers,
        },
        body: JSON.stringify({ messages: [{ role: "user", parts: [{ type: "text", text: "hi" }] }] }),
      });
    }

    beforeEach(() => {
      vi.mocked(resolveChatTenantContext).mockResolvedValue(dashboardCtx as never);
      process.env.DIGICHAT_PLAN_PROOF_SECRET = PLAN_PROOF_SECRET;
    });

    afterEach(() => {
      delete process.env.DIGICHAT_PLAN_PROOF_SECRET;
    });

    it("serves well past the free-turn cap with no 402 and never touches the trial quota", async () => {
      const { signPlanProof } = await import("@/lib/plan-proof");
      const proof = signPlanProof("desk", PLAN_PROOF_SECRET);
      const quotaModule = await import("@/lib/embed-turn-quota");
      const overSpy = vi.spyOn(quotaModule, "isOverEmbedTrialLimit");
      const recordSpy = vi.spyOn(quotaModule, "recordEmbedTrialTurn");
      const unlockSpy = vi.spyOn(quotaModule, "unlockEmbedTrial");
      try {
        for (let i = 0; i < EMBED_FREE_TURN_LIMIT + 2; i++) {
          const res = await POST(dashboardReq({ "x-embed-plan-proof": proof }));
          expect(res.status).toBe(200);
        }
        expect(overSpy).not.toHaveBeenCalled();
        expect(recordSpy).not.toHaveBeenCalled();
        expect(unlockSpy).not.toHaveBeenCalled();
      } finally {
        overSpy.mockRestore();
        recordSpy.mockRestore();
        unlockSpy.mockRestore();
      }
    });

    it("returns 403 plan_tier_required when no proof is supplied (#3662)", async () => {
      const req = dashboardReq();
      const res = await POST(req);
      expect(res.status).toBe(403);
      const body = (await res.json()) as { error: string };
      expect(body.error).toBe("plan_tier_required");
    });

    it("does not let the DIG-613 monitor identity bypass the plan-tier gate", async () => {
      // The monitor bypass is scoped to the trial_form free-turn gate. It must
      // not become a general capability: the plan-tier check runs before it and
      // nothing about it consults the monitor allowlist.
      process.env.DIGICHAT_MONITOR_TOKENS =
        "monitor-secret-0123456789abcdef0123456789abcdef";
      const res = await POST(
        dashboardReq({
          "x-embed-monitor-token": "monitor-secret-0123456789abcdef0123456789abcdef",
        }),
      );
      expect(res.status).toBe(403);
      const body = (await res.json()) as { error: string };
      expect(body.error).toBe("plan_tier_required");
    });

    it("returns 403 when X-Embed-Plan-Tier header is spoofed (#3662 Chris lock)", async () => {
      // Raw X-Embed-Plan-Tier header is NEVER trusted — must still 403.
      const req = dashboardReq({ "x-embed-plan-tier": "desk" });
      const res = await POST(req);
      expect(res.status).toBe(403);
      const body = (await res.json()) as { error: string };
      expect(body.error).toBe("plan_tier_required");
    });

    it("returns 403 when ?plan_tier= query param is spoofed (#3662 Chris lock)", async () => {
      // Raw ?plan_tier= query param is NEVER trusted — must still 403.
      const req = new Request("http://localhost/api/chat?plan_tier=desk", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://digiquant.io",
        },
        body: JSON.stringify({ messages: [{ role: "user", parts: [{ type: "text", text: "hi" }] }] }),
      });
      const res = await POST(req);
      expect(res.status).toBe(403);
    });

    it("allows chat when HMAC proof is desk+", async () => {
      const { signPlanProof } = await import("@/lib/plan-proof");
      for (const tier of ["desk", "studio", "enterprise"]) {
        const proof = signPlanProof(tier as "desk" | "studio" | "enterprise", PLAN_PROOF_SECRET);
        const req = dashboardReq({ "x-embed-plan-proof": proof });
        const res = await POST(req);
        expect(res.status).toBe(200);
      }
    });

    it("returns 403 when HMAC proof is free/brief", async () => {
      const { signPlanProof } = await import("@/lib/plan-proof");
      for (const tier of ["free", "brief"]) {
        const proof = signPlanProof(tier as "free" | "brief", PLAN_PROOF_SECRET);
        const req = dashboardReq({ "x-embed-plan-proof": proof });
        const res = await POST(req);
        expect(res.status).toBe(403);
        const body = (await res.json()) as { error: string };
        expect(body.error).toBe("plan_tier_required");
      }
    });

    it("returns 403 when HMAC proof has wrong secret", async () => {
      const { signPlanProof } = await import("@/lib/plan-proof");
      const proof = signPlanProof("desk", "wrong-secret");
      const req = dashboardReq({ "x-embed-plan-proof": proof });
      const res = await POST(req);
      expect(res.status).toBe(403);
    });

    it("returns 403 when HMAC proof is expired", async () => {
      const { signPlanProof } = await import("@/lib/plan-proof");
      const proof = signPlanProof("desk", PLAN_PROOF_SECRET, Date.now() - 1000);
      const req = dashboardReq({ "x-embed-plan-proof": proof });
      const res = await POST(req);
      expect(res.status).toBe(403);
    });

    it("returns 403 when HMAC proof is tampered", async () => {
      const { signPlanProof } = await import("@/lib/plan-proof");
      const proof = signPlanProof("desk", PLAN_PROOF_SECRET);
      // Tamper with the proof by flipping a character
      const tampered = proof.slice(0, -2) + (proof.slice(-2) === "AA" ? "BB" : "AA");
      const req = dashboardReq({ "x-embed-plan-proof": tampered });
      const res = await POST(req);
      expect(res.status).toBe(403);
    });

    it("allows chat via authenticated session plan_tier (not embed proof)", async () => {
      // When the user is authenticated via digichat session (not embed),
      // the plan_tier from the JWT session is used as fallback.
      vi.mocked(resolveChatTenantContext).mockResolvedValue({
        tenantSlug: "digiquant-dashboard",
        ownerUserSub: "user:123",
      } as never);
      vi.mocked(requireDigiChatAuth).mockResolvedValue({
        tenantSlug: "digiquant-dashboard",
        ownerUserSub: "user:123",
        plan_tier: "desk",
      });
      const req = dashboardReq();
      const res = await POST(req);
      expect(res.status).toBe(200);
    });

    it("returns 403 when session plan_tier is free/brief", async () => {
      vi.mocked(resolveChatTenantContext).mockResolvedValue({
        tenantSlug: "digiquant-dashboard",
        ownerUserSub: "user:123",
        embedConfig: dashboardCtx.embedConfig,
      } as never);
      vi.mocked(requireDigiChatAuth).mockResolvedValue({
        tenantSlug: "digiquant-dashboard",
        ownerUserSub: "user:123",
        plan_tier: "free",
      });
      const req = dashboardReq();
      const res = await POST(req);
      expect(res.status).toBe(403);
    });

    it("showByok is true in the embed config (contract test)", () => {
      expect(dashboardCtx.embedConfig.showByok).toBe(true);
    });
  });
  describe("DIG-4589: one source decides the session lock and the model allowlist", () => {
    // The embed tenant registry and the deployment config are two sources
    // that can disagree. The loader merges them once, so the route reads the
    // lock and the allowlist from ONE artefact: the request's tenant, which
    // in production is the projection of the merged host deployment. These
    // tests drive the real embed tenant resolution, so the tenant the route
    // sees has the production shape.
    const OCC_HOST = "occ.digithings.ai";
    const OCC_TOKEN = "occ-secret";

    // A deployment host with NO model list. Since #6237 every product chat
    // (the OCC host is one) resolves a catalog list even when the YAML has
    // no `models` block, so "this tenant has no list" has to be said
    // explicitly. `allowPicker: false` is the operator's way of saying it,
    // and it is the shape Counsel's DIG-4486 ruling gives a locked OCC
    // tenant: no picker, no hand list, the operator's model only.
    const NO_MODEL_LIST = ["    models:", "      allowPicker: false"];

    function occYaml(opts: { host?: string[]; deployment?: string[] } = {}): string {
      return [
        "version: 1",
        ...(opts.deployment ? ["deployment:", ...opts.deployment] : []),
        "hosts:",
        `  ${OCC_HOST}:`,
        "    slug: occ",
        `    token: ${OCC_TOKEN}`,
        "    backend:",
        "      type: digigraph",
        ...(opts.host ?? []),
        "",
      ].join("\n");
    }

    function installConfig(yaml: string, tenant: Record<string, unknown>): void {
      setDigichatConfigForTests(
        loadDigichatConfig({
          fileContents: yaml,
          env: {
            DIGICHAT_EMBED_TENANTS: JSON.stringify({ [OCC_HOST]: tenant }),
          },
        }),
      );
    }

    function occReq(headers: Record<string, string> = {}): Request {
      return new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": `https://${OCC_HOST}`,
          "x-embed-token": OCC_TOKEN,
          ...headers,
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      });
    }

    // A referer-resolved tenant: the browser sends no X-Embed-Host, so the
    // host comes from the Referer. The route must decide from the tenant it
    // resolved, never from the header-only deployment lookup.
    function occRefererReq(headers: Record<string, string> = {}): Request {
      return new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          referer: `https://${OCC_HOST}/embed`,
          "x-embed-token": OCC_TOKEN,
          ...headers,
        },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      });
    }

    /** Captures the model the route forwards to digigraph. */
    function captureForwardedModel(): string[] {
      const forwarded: string[] = [];
      vi.mocked(createDigiGraphClient).mockImplementation(
        (() =>
          ((modelId: string) => {
            forwarded.push(modelId);
            return {};
          }) as never) as never,
      );
      return forwarded;
    }

    beforeEach(() => {
      // The embed surface: auth refuses, the route resolves the embed tenant.
      vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    });

    afterEach(() => {
      resetDigichatConfigForTests();
      vi.mocked(createDigiGraphClient).mockImplementation(
        (() => (() => ({})) as never) as never,
      );
    });

    it("enforces the tenant model offer when the deployment config has no list", async () => {
      // The tenant curates the offer; the deployment config has no model
      // list. Before the fix the empty deployment list won, so no allowlist
      // ran and any x-digi-model was forwarded unchecked.
      installConfig(occYaml(), {
        slug: "occ",
        token: OCC_TOKEN,
        gateMode: "ungated",
        backend: { type: "digigraph" },
        models: { default: "only-this-model", available: ["only-this-model"] },
      });

      const denied = await POST(occReq({ "x-digi-model": "other-model" }));
      expect(denied.status).toBe(400);
      const body = (await denied.json()) as { error: string };
      expect(body.error).toBe("model_not_allowed");

      const allowed = await POST(occReq({ "x-digi-model": "only-this-model" }));
      expect(allowed.status).toBe(200);
    });

    it("honours the pick from a locked tenant's own curated list", async () => {
      // The live OCC shape: the tenant is locked AND curates its own model
      // list. The lock pins the session controls, but the picker is the
      // operator's own list, so a pick from that list is forwarded. The
      // deployment host in this fixture also resolves a catalog (every
      // product chat does since #6237), so this also pins that the merge
      // lets the tenant's hand list win instead of letting the catalog
      // ignore it and pin the tenant's default against a catalog that does
      // not know it.
      installConfig(occYaml(), {
        slug: "occ",
        token: OCC_TOKEN,
        gateMode: "ungated",
        backend: { type: "digigraph" },
        lockSessionControls: true,
        models: { default: "only-this-model", available: ["only-this-model"] },
      });

      const forwarded = captureForwardedModel();
      const res = await POST(occReq({ "x-digi-model": "only-this-model" }));
      expect(res.status).toBe(200);
      expect(forwarded).toEqual(["only-this-model"]);
    });

    it("honours a session lock set in the deployment config", async () => {
      // The lock is set in the deployment config only. The merged tenant
      // carries it, so the visitor's model pick is never forwarded.
      installConfig(
        occYaml({
          host: [
            "    gate:",
            "      mode: ungated",
            "      lockSessionControls: true",
            ...NO_MODEL_LIST,
          ],
        }),
        {
          slug: "occ",
          token: OCC_TOKEN,
          gateMode: "ungated",
          backend: { type: "digigraph" },
        },
      );

      const forwarded = captureForwardedModel();
      const res = await POST(occReq({ "x-digi-model": "some-model" }));
      expect(res.status).toBe(200);
      // The house default, never the visitor's pick.
      expect(forwarded).toEqual(["digigraph"]);
    });

    it("never drops a session lock set in the tenant registry", async () => {
      // The mirror image: the lock is set in the tenant registry while the
      // deployment config has a host for the same host without a lock. The
      // merge keeps the stricter of the two, so the pick is not forwarded.
      installConfig(occYaml({ host: NO_MODEL_LIST }), {
        slug: "occ",
        token: OCC_TOKEN,
        gateMode: "ungated",
        backend: { type: "digigraph" },
        lockSessionControls: true,
      });

      const forwarded = captureForwardedModel();
      const res = await POST(occReq({ "x-digi-model": "some-model" }));
      expect(res.status).toBe(200);
      expect(forwarded).toEqual(["digigraph"]);
    });

    it("keeps the tenant's own lock when the default deployment locks another tenant", async () => {
      // The config has a default `deployment:` block (locked) and an OCC host
      // (not locked). The tenant is resolved from the Referer, so the
      // header-only deployment lookup falls back to the default deployment.
      // The tenant's own lock decides: OCC is not locked.
      installConfig(
        occYaml({
          deployment: [
            "  slug: default",
            "  backend:",
            "    type: digigraph",
            "  gate:",
            "    mode: ungated",
            "    lockSessionControls: true",
          ],
          host: NO_MODEL_LIST,
        }),
        {
          slug: "occ",
          token: OCC_TOKEN,
          gateMode: "ungated",
          backend: { type: "digigraph" },
        },
      );

      const forwarded = captureForwardedModel();
      const res = await POST(occRefererReq({ "x-digi-model": "some-model" }));
      expect(res.status).toBe(200);
      expect(forwarded).toEqual(["some-model"]);
    });

    it("merges a registry tenant into an origin-form deployment host key", async () => {
      // The deployment config keys the host as an origin, the registry keys it
      // as a bare host. The lookup normalises both, so the merge has to as
      // well — otherwise the host ends up with two entries and the
      // registry-only duplicate wins, dropping the deployment's own gate.
      installConfig(
        [
          "version: 1",
          "hosts:",
          `  "https://${OCC_HOST}":`,
          "    slug: occ",
          `    token: ${OCC_TOKEN}`,
          "    backend:",
          "      type: digigraph",
          "    gate:",
          "      mode: ungated",
          "      lockSessionControls: true",
          "",
        ].join("\n"),
        {
          slug: "occ",
          token: OCC_TOKEN,
          gateMode: "ungated",
          backend: { type: "digigraph" },
        },
      );

      const forwarded = captureForwardedModel();
      const res = await POST(occReq({ "x-digi-model": "some-model" }));
      expect(res.status).toBe(200);
      // The deployment's lock survived the merge and still pins the model.
      expect(forwarded).toEqual(["digigraph"]);
    });
  });

  describe("trace stream (the production default)", () => {
    // Every other test in this file pins DIGICHAT_TRACE_UI="0", which routes through
    // `streamText`. Production does the opposite: the flag is unset, so `useTraceStream`
    // is true and the request goes to `createDigigraphTraceStreamResponse` instead. The
    // header assertions above therefore only ever observed the *fallback* branch — the
    // branch production actually takes was uncovered, mock included.
    beforeEach(() => {
      delete process.env.DIGICHAT_TRACE_UI;
    });

    function chatReq(headers: Record<string, string> = {}): Request {
      return new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json", ...headers },
        body: JSON.stringify({
          messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
        }),
      });
    }

    it("takes the trace adapter, not streamText, when nothing opts out", async () => {
      vi.mocked(streamText).mockClear();
      const res = await POST(chatReq());
      expect(res.status).toBe(200);
      expect(createDigigraphTraceStreamResponse).toHaveBeenCalledTimes(1);
      expect(streamText).not.toHaveBeenCalled();
    });

    it("forwards tenant and BYOK upstream headers to the trace adapter", async () => {
      await POST(
        chatReq({
          "x-byok-key": "sk-or-v1-test",
          "x-byok-provider": "openrouter",
          "x-byok-model": "openai/gpt-4o-mini",
          "x-digichat-session": "sess-trace",
          "x-request-id": "rid-trace",
        })
      );
      const call = vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0];
      expect(call?.upstreamHeaders["X-BYOK-Key"]).toBe("sk-or-v1-test");
      expect(call?.upstreamHeaders["X-BYOK-Provider"]).toBe("openrouter");
      expect(call?.upstreamHeaders["X-BYOK-Model"]).toBe("openai/gpt-4o-mini");
      expect(call?.upstreamHeaders["X-Digichat-Tenant"]).toBe(mockAuthCtx.tenantSlug);
      // `route.ts:241-242` emits both spellings, and the short one is the only one
      // digigraph actually consumes (`corpus_routing.py:39`) — so assert it too.
      expect(call?.upstreamHeaders["X-Digi-Tenant"]).toBe(mockAuthCtx.tenantSlug);
      // The adapter carries no Authorization of its own (#2537 removed the dead
      // second source), so this header is the *only* thing authenticating the
      // upstream call. Unpinned, deleting `route.ts:244` outright left all 622
      // digichat tests green — a future conditional Authorization would ship a
      // silently unauthenticated request to digigraph.
      expect(call?.upstreamHeaders.Authorization).toMatch(/^Bearer .+/);
      expect(call?.digigraphBaseUrl).toBe("http://127.0.0.1:8000");
      // The conversation itself, and the headers this branch echoes back to the
      // browser. The mock factory discards its argument and answers a bare 200, so
      // neither is observable through the response — assert on the recorded call or
      // the trace branch could hand the adapter an empty history and still pass.
      expect(call?.messages).toHaveLength(1);
      expect(call?.messages?.[0]).toMatchObject({
        role: "user",
        parts: [{ type: "text", text: "hi" }],
      });
      expect(call?.responseHeaders["X-Digichat-Session"]).toBe("sess-trace");
      expect(call?.responseHeaders["X-Request-Id"]).toBe("rid-trace");
      // The session path now resolves the same deployment the embed path does
      // (Phase 2b), so the adapter gets that deployment's `gate.activityDetail`
      // instead of a hard-coded "full". The synthetic dev config in tests leaves
      // it at the schema default.
      expect(call?.activityDetail).toBe("labels");
      expect(call?.signal).toBeDefined();
    });

    it("forwards a digigraph-backed embed's activityDetail to the trace adapter", async () => {
      // The default above only exercises the `?? "full"` fallback. The one fixture
      // that sets `activityDetail` elsewhere in this file is `foundry`-backed, and
      // `route.ts:182` returns before the trace branch — so nothing pinned that a
      // *configured* value reaches the adapter at all.
      vi.mocked(resolveChatTenantContext).mockResolvedValue({
        tenantSlug: "occ",
        ownerUserSub: "embed:anonymous",
        embedConfig: {
          slug: "occ",
          gateMode: "ungated",
          theme: "dark",
          attribution: false,
          token: "tok",
          backend: { type: "digigraph", digisearchIndex: "occ_help" },
          activityDetail: "labels",
        },
      } as never);
      await POST(chatReq({ "x-embed-host": "https://occ.example" }));
      const call = vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0];
      expect(call?.activityDetail).toBe("labels");
      expect(call?.upstreamHeaders["X-Digi-Corpus-Index"]).toBe("occ_help");
    });

    it("falls back to streamText when the caller sends x-digichat-trace: 0", async () => {
      vi.mocked(streamText).mockClear();
      const res = await POST(chatReq({ "x-digichat-trace": "0" }));
      expect(res.status).toBe(200);
      expect(createDigigraphTraceStreamResponse).not.toHaveBeenCalled();
      expect(streamText).toHaveBeenCalledTimes(1);
    });

    describe("baseline embed research prompt", () => {
      // digraph derives the research system prompt server-side (project config
      // `agents.research_system_prompt` / tenant `DIGI_TENANT_CORPUS_MAP`). The BFF
      // must never send `research_system_prompt`: digraph accepts-but-ignores the old
      // client field, and a client-supplied system prompt is not a trust path.
      function lastTraceOpts(): Record<string, unknown> | undefined {
        return vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0] as
          | Record<string, unknown>
          | undefined;
      }

      it("never sends the prompt on the real unauthenticated baseline embed path", async () => {
        // True baseline: no session (auth rejects) + unknown host + legacy
        // generic embed open. resolveEmbedChatTenant is real here and must
        // yield { tenantSlug: "embed", embedConfig: null }.
        process.env.DIGICHAT_LEGACY_EMBED_ENABLED = "1";
        vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
        const res = await POST(chatReq({ "x-embed-host": "https://unknown.example" }));
        expect(res.status).toBe(200);
        const opts = lastTraceOpts();
        expect(opts).toBeDefined();
        expect(opts).not.toHaveProperty("researchSystemPrompt");
        expect(opts).not.toHaveProperty("research_system_prompt");
      });

      it("never sends the prompt for a matched host deployment", async () => {
        setDigichatConfigForTests(
          parseDigichatConfig({
            version: 1,
            deployment: { slug: "local", backend: { type: "digigraph" } },
            hosts: {
              "matched.example": {
                slug: "matched",
                backend: { type: "digigraph" },
              },
            },
          })
        );
        try {
          const res = await POST(chatReq({ "x-embed-host": "https://matched.example" }));
          expect(res.status).toBe(200);
          expect(lastTraceOpts()).not.toHaveProperty("researchSystemPrompt");
        } finally {
          resetDigichatConfigForTests();
        }
      });
    });

    describe("the session path honours the deployment config (Phase 2b)", () => {
      // `resolveChatTenantContext` is mocked to `mockAuthCtx`, which carries no
      // `embedConfig` — so these requests are the authenticated-session surface,
      // exactly where the deployment config used to be ignored.
      it("routes a session request to the deployment's foundry backend", async () => {
        setDigichatConfigForTests(
          parseDigichatConfig({
            version: 1,
            deployment: {
              slug: "client",
              backend: {
                type: "foundry",
                projectEndpoint: "https://example.openai.azure.com",
                agentName: "agent-1",
              },
            },
          })
        );
        try {
          vi.mocked(createFoundryStreamResponse).mockClear();
          const res = await POST(chatReq());
          expect(res.status).toBe(200);
          expect(createFoundryStreamResponse).toHaveBeenCalledTimes(1);
          const opts = vi.mocked(createFoundryStreamResponse).mock.calls.at(-1)?.[0] as {
            projectEndpoint: string;
            agentName: string;
          };
          expect(opts.projectEndpoint).toBe("https://example.openai.azure.com");
          expect(opts.agentName).toBe("agent-1");
        } finally {
          resetDigichatConfigForTests();
        }
      });

      it("forwards the digigraph corpus index and vault prefix on a session request", async () => {
        setDigichatConfigForTests(
          parseDigichatConfig({
            version: 1,
            deployment: {
              slug: "client",
              backend: {
                type: "digigraph",
                digisearchIndex: "idx-1",
                vaultPathPrefix: "notes/",
              },
            },
          })
        );
        try {
          const res = await POST(chatReq());
          expect(res.status).toBe(200);
          const opts = vi.mocked(createDigigraphTraceStreamResponse).mock.calls.at(-1)?.[0] as {
            upstreamHeaders: Record<string, string>;
          };
          expect(opts.upstreamHeaders["X-Digi-Corpus-Index"]).toBe("idx-1");
          expect(opts.upstreamHeaders["X-Digi-Vault-Prefix"]).toBe("notes/");
        } finally {
          resetDigichatConfigForTests();
        }
      });

      it("enforces the deployment's requiredPlanTier on a session request", async () => {
        setDigichatConfigForTests(
          parseDigichatConfig({
            version: 1,
            deployment: {
              slug: "client",
              backend: { type: "digigraph" },
              gate: { mode: "ungated", activityDetail: "labels", requiredPlanTier: "studio" },
            },
          })
        );
        try {
          const res = await POST(chatReq());
          expect(res.status).toBe(403);
          const body = (await res.json()) as { error: string };
          expect(body.error).toBe("plan_tier_required");
        } finally {
          resetDigichatConfigForTests();
        }
      });

      it("runs the models.available allowlist ahead of the foundry branch", async () => {
        setDigichatConfigForTests(
          parseDigichatConfig({
            version: 1,
            deployment: {
              slug: "client",
              backend: {
                type: "foundry",
                projectEndpoint: "https://example.openai.azure.com",
                agentName: "agent-1",
              },
              models: { available: ["only-this-model"] },
            },
          })
        );
        try {
          vi.mocked(createFoundryStreamResponse).mockClear();
          const res = await POST(chatReq({ "x-digi-model": "some-other-model" }));
          expect(res.status).toBe(400);
          const body = (await res.json()) as { error: string };
          expect(body.error).toBe("model_not_allowed");
          expect(createFoundryStreamResponse).not.toHaveBeenCalled();

          // An allowlisted model must pass the allowlist and reach the foundry
          // branch — which only happens because the allowlist now runs first.
          vi.mocked(createFoundryStreamResponse).mockClear();
          const ok = await POST(chatReq({ "x-digi-model": "only-this-model" }));
          expect(ok.status).toBe(200);
          expect(createFoundryStreamResponse).toHaveBeenCalledTimes(1);
        } finally {
          resetDigichatConfigForTests();
        }
      });

      it("routes a session request to the deployment's AI-SDK backend (#4535)", async () => {
        setDigichatConfigForTests(
          parseDigichatConfig({
            version: 1,
            deployment: {
              slug: "client",
              backend: {
                type: "openai-responses",
                baseUrl: "https://api.example.com/v1",
                model: "gpt-4o-mini",
                apiKeyEnv: "DIGICHAT_BACKEND_EXAMPLE_KEY",
              },
            },
          })
        );
        try {
          const res = await POST(chatReq());
          expect(res.status).toBe(200);
          const opts = vi.mocked(createAiSdkStreamResponse).mock.calls.at(-1)?.[0] as {
            backend: { type: string; model: string };
          };
          expect(opts.backend.type).toBe("openai-responses");
          expect(opts.backend.model).toBe("gpt-4o-mini");
          // The digigraph fallback must not run for an AI-SDK backend.
          expect(createDigigraphTraceStreamResponse).not.toHaveBeenCalled();
        } finally {
          resetDigichatConfigForTests();
        }
      });

      it("passes the web-search gate to the AI-SDK backend (#4552)", async () => {
        setDigichatConfigForTests(
          parseDigichatConfig({
            version: 1,
            deployment: {
              slug: "client",
              backend: {
                type: "openai-responses",
                baseUrl: "https://api.example.com/v1",
                model: "gpt-4o-mini",
                apiKeyEnv: "DIGICHAT_BACKEND_EXAMPLE_KEY",
              },
              gate: { mode: "ungated", webSearch: true },
            },
          })
        );
        try {
          await POST(chatReq({ "x-digi-enable-web-search": "1" }));
          const withHeader = vi.mocked(createAiSdkStreamResponse).mock.calls.at(-1)?.[0] as {
            webSearch?: boolean;
          };
          expect(withHeader.webSearch).toBe(true);

          // The tenant allows it, but the client never asked: stays off.
          await POST(chatReq());
          const withoutHeader = vi
            .mocked(createAiSdkStreamResponse)
            .mock.calls.at(-1)?.[0] as { webSearch?: boolean };
          expect(withoutHeader.webSearch).toBe(false);
        } finally {
          resetDigichatConfigForTests();
        }
      });
    });
  });
});
