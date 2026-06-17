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

vi.mock("ai", () => ({
  convertToModelMessages: vi.fn(async (m: unknown[]) => m),
  streamText: vi.fn(() => ({
    toUIMessageStreamResponse: vi.fn(({ headers }: { headers: Record<string, string> }) =>
      new Response("stream", { status: 200, headers })
    ),
  })),
  smoothStream: vi.fn(() => ({})),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { resolveChatTenantContext } from "@/lib/chat-route-context";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
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
});
