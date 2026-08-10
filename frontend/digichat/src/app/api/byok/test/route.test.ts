import { beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));

vi.mock("@/lib/embed-chat-tenant", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/embed-chat-tenant")>();
  return {
    ...actual,
    resolveEmbedChatTenant: vi.fn(actual.resolveEmbedChatTenant),
  };
});

vi.mock("@/lib/embed-ip-rate-limit", () => ({
  checkEmbedIpRateLimit: vi.fn(() => ({ allowed: true, retryAfterSec: 0 })),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { resolveEmbedChatTenant } from "@/lib/embed-chat-tenant";
import { checkEmbedIpRateLimit } from "@/lib/embed-ip-rate-limit";

describe("POST /api/byok/test", () => {
  beforeEach(() => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(checkEmbedIpRateLimit).mockReturnValue({
      allowed: true,
      retryAfterSec: 0,
    });
  });

  it("returns 401 without auth when not an embed request", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: { "x-byok-key": "sk-test" },
      })
    );
    expect(res.status).toBe(401);
  });

  it("admits anonymous embed requests with X-Embed-Host (no DigiChat session)", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    vi.mocked(resolveEmbedChatTenant).mockReturnValue({
      tenantSlug: "digithings",
      ownerUserSub: "embed:anonymous",
      embedConfig: null,
    });
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: [{ id: "gpt-4o-mini" }] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: {
            "x-byok-key": "sk-test",
            "x-byok-provider": "openai",
            "x-embed-host": "https://digithings.ai",
          },
        }),
      );
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.ok).toBe(true);
      expect(resolveEmbedChatTenant).toHaveBeenCalled();
      expect(checkEmbedIpRateLimit).toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("returns 400 when BYOK key header missing", async () => {
    const res = await POST(new Request("http://localhost/api/byok/test", { method: "POST" }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.ok).toBe(false);
  });

  it("returns 400 for invalid OpenAI key prefix", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: { "x-byok-key": "not-a-key", "x-byok-provider": "openai" },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("sk-");
  });

  it("returns 400 for invalid OpenRouter key prefix", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: {
          "x-byok-key": "sk-proj-bad",
          "x-byok-provider": "openrouter",
          "x-byok-model": "openai/gpt-4o-mini",
        },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("sk-or-");
  });

  it("returns 400 when OpenRouter model header missing", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: {
          "x-byok-key": "sk-or-v1-test",
          "x-byok-provider": "openrouter",
        },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("Model is required");
  });

  it("returns 400 for invalid Gemini key prefix", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: {
          "x-byok-key": "not-gemini",
          "x-byok-provider": "gemini",
          "x-byok-model": "gemini/gemini-2.0-flash",
        },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("AI");
  });

  it("returns 400 when Gemini model header missing", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: {
          "x-byok-key": "AIza-test",
          "x-byok-provider": "gemini",
        },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("Model is required");
  });
});
