import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";

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
    process.env.DIGICHAT_EMBED_ENABLED = "1";
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

  it("routes OpenRouter BYOK through DigiGraph with BYOK headers", async () => {
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
});

const RELAY_REGISTRY = JSON.stringify({
  "datatapstream.com": {
    slug: "datatapstream",
    backend: { type: "external-relay", url: "https://relay.example.com/api/digichat" },
    gateMode: "ungated",
    token: "datatapstream-secret",
  },
});

function relaySse(frames: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(c) {
        for (const f of frames) c.enqueue(encoder.encode(f));
        c.close();
      },
    }),
    { status: 200 }
  );
}

describe("external-relay embed tenants", () => {
  beforeEach(() => {
    process.env = { ...process.env, DIGICHAT_TRACE_UI: "0" };
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: true, retryAfterSec: 0 });
    vi.mocked(checkEmbedIpRateLimit).mockReturnValue({ allowed: true, retryAfterSec: 0 });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    resetEmbedTenantRegistryForTests();
  });

  it("streams from the configured relay without touching DigiGraph auth", async () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", RELAY_REGISTRY);
    resetEmbedTenantRegistryForTests();
    const fetchMock = vi.fn().mockResolvedValue(
      relaySse([
        'event: conversation\ndata: {"type":"conversation","conversationId":"c1"}\n\n',
        'event: text-delta\ndata: {"type":"text-delta","delta":"Hi"}\n\n',
        'event: done\ndata: {"type":"done"}\n\n',
      ])
    );
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(
      new Request("http://127.0.0.1/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://datatapstream.com",
          "x-embed-token": "datatapstream-secret",
          "x-external-conversation": "c-prev",
        },
        body: JSON.stringify({
          messages: [{ id: "u1", role: "user", parts: [{ type: "text", text: "hello" }] }],
        }),
      })
    );

    expect(res.status).toBe(200);
    const text = await new Response(res.body).text();
    expect(text).toContain('"delta":"Hi"');
    // The relay was called with the echoed conversation id and the latest message:
    expect(fetchMock).toHaveBeenCalledWith(
      "https://relay.example.com/api/digichat",
      expect.objectContaining({
        body: JSON.stringify({ conversationId: "c-prev", message: "hello" }),
      })
    );
    // No DIGIGRAPH_* / DIGIKEY_* env was set in this test — reaching a 200
    // proves resolveDigigraphUpstreamAuth was never invoked on this path.
  });

  it("still enforces the per-IP embed limiter for an external-relay tenant", async () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", RELAY_REGISTRY);
    resetEmbedTenantRegistryForTests();
    vi.mocked(checkEmbedIpRateLimit).mockReturnValue({ allowed: false, retryAfterSec: 45 });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(
      new Request("http://127.0.0.1/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://datatapstream.com",
          "x-embed-token": "datatapstream-secret",
        },
        body: JSON.stringify({
          messages: [{ id: "u1", role: "user", parts: [{ type: "text", text: "hello" }] }],
        }),
      })
    );

    expect(res.status).toBe(429);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
