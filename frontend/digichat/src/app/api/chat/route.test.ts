import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));

vi.mock("@/lib/chat-route-context", () => ({
  resolveChatTenantContext: vi.fn(),
}));

vi.mock("@/lib/bff-rate-limit", () => ({
  checkBffRateLimit: vi.fn(() => ({ allowed: true, retryAfterSec: 0 })),
}));

vi.mock("@/lib/embed-ip-rate-limit", () => ({
  checkEmbedIpRateLimit: vi.fn(() => ({ allowed: true, retryAfterSec: 0 })),
  clientIpForRateLimit: vi.fn(() => "127.0.0.1"),
}));

vi.mock("@/lib/adapters/foundry/stream", () => ({
  createFoundryStreamResponse: vi.fn(async () => new Response("foundry", { status: 200 })),
}));

vi.mock("@/lib/digigraph-upstream", () => ({
  resolveDigigraphUpstreamAuth: vi.fn(),
  DigigraphUpstreamAuthError: class DigigraphUpstreamAuthError extends Error {},
}));

vi.mock("@/lib/ecosystem", () => ({
  getEcosystemEndpoints: vi.fn(async () => ({
    digigraphUrl: "http://127.0.0.1:8000",
    digiquantUrl: "http://127.0.0.1:8001",
    digismithUrl: "http://127.0.0.1:8003",
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
      toUIMessageStreamResponse: vi.fn(({ headers }: { headers: Record<string, string> }) =>
        new Response("stream", { status: 200, headers })
      ),
    })),
    smoothStream: vi.fn(() => ({})),
  };
});

import { requireDigiChatAuth } from "@/lib/request-auth";
import { resolveChatTenantContext } from "@/lib/chat-route-context";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import { checkEmbedIpRateLimit } from "@/lib/embed-ip-rate-limit";
import { resolveDigigraphUpstreamAuth } from "@/lib/digigraph-upstream";
import { createFoundryStreamResponse } from "@/lib/adapters/foundry/stream";
import { resetEmbedTrialQuotaForTests } from "@/lib/embed-turn-quota";
import { EMBED_FREE_TURN_LIMIT } from "@/lib/embed-turn-limits";
import { streamText } from "ai";

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
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: true, retryAfterSec: 0 });
    vi.mocked(checkEmbedIpRateLimit).mockReturnValue({ allowed: true, retryAfterSec: 0 });
    resetEmbedTrialQuotaForTests();
    vi.mocked(createFoundryStreamResponse).mockClear();
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

    it("skips the quota entirely when the client IP is unknown, so a broken ingress fails open rather than collapsing every visitor into one bucket", async () => {
      const { clientIpForRateLimit } = await import("@/lib/embed-ip-rate-limit");
      const spy = vi.mocked(clientIpForRateLimit).mockReturnValue("unknown");
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
});
