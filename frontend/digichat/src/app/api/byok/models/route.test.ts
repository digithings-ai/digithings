import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));
vi.mock("@/lib/embed-chat-tenant", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/embed-chat-tenant")>();
  return { ...actual, resolveEmbedChatTenant: vi.fn(actual.resolveEmbedChatTenant) };
});
vi.mock("@/lib/embed-ip-rate-limit", () => ({
  checkEmbedIpRateLimit: vi.fn(() => ({ allowed: true, retryAfterSec: 0 })),
}));
vi.mock("@/lib/bff-rate-limit", () => ({
  checkBffRateLimit: vi.fn(() => ({ allowed: true })),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { resolveEmbedChatTenant } from "@/lib/embed-chat-tenant";
import { checkEmbedIpRateLimit } from "@/lib/embed-ip-rate-limit";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";

function req(url: string, headers: Record<string, string> = {}) {
  return new Request(`http://localhost${url}`, { headers });
}

describe("GET /api/byok/models", () => {
  beforeEach(() => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: true });
  });

  it("returns 401 without auth and not an embed request", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    const res = await GET(req("/api/byok/models?provider=openrouter"));
    expect(res.status).toBe(401);
  });

  it("returns 400 for any provider other than openrouter", async () => {
    const res = await GET(req("/api/byok/models?provider=openai"));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBe("unsupported_provider");
  });

  it("rate-limits authenticated callers too, not just embed", async () => {
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: false, retryAfterSec: 5 });
    const res = await GET(req("/api/byok/models?provider=openrouter"));
    expect(res.status).toBe(429);
    expect(res.headers.get("retry-after")).toBe("5");
    expect(checkBffRateLimit).toHaveBeenCalled();
  });

  it("rate-limits the embed path too, once it clears the embed-IP check", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    vi.mocked(resolveEmbedChatTenant).mockReturnValue({
      tenantSlug: "digithings",
      ownerUserSub: "embed:anonymous",
      embedConfig: null,
    });
    vi.mocked(checkEmbedIpRateLimit).mockReturnValue({ allowed: true, retryAfterSec: 0 });
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: false, retryAfterSec: 5 });
    const res = await GET(
      req("/api/byok/models?provider=openrouter", { "x-embed-host": "https://digithings.ai" }),
    );
    expect(res.status).toBe(429);
    expect(res.headers.get("retry-after")).toBe("5");
    expect(checkBffRateLimit).toHaveBeenCalled();
  });

  it("fetches OpenRouter's public catalog with no key forwarded and buckets it", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [{ id: "openai/gpt-oss-20b:free", pricing: { prompt: "0", completion: "0" } }] }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res = await GET(req("/api/byok/models?provider=openrouter"));
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.ok).toBe(true);
      expect(body.free).toHaveLength(1);
      const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("https://openrouter.ai/api/v1/models");
      expect((init.headers as Record<string, string> | undefined)?.["Authorization"]).toBeUndefined();
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("returns 502 and never throws on a malformed upstream response", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ not_data: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    try {
      const res = await GET(req("/api/byok/models?provider=openrouter"));
      expect(res.status).toBe(502);
      const body = await res.json();
      expect(body.error).toBe("malformed_response");
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("returns 502 on an oversized response without buffering it fully", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: { "content-type": "application/json", "content-length": String(3_000_000) },
      }),
    );
    try {
      const res = await GET(req("/api/byok/models?provider=openrouter"));
      expect(res.status).toBe(502);
      const body = await res.json();
      expect(body.error).toBe("response_too_large");
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("returns 502 when the upstream request errors/times out without leaking internals", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("getaddrinfo EAI_AGAIN openrouter.ai"));
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const res = await GET(req("/api/byok/models?provider=openrouter"));
      expect(res.status).toBe(502);
      const body = await res.json();
      expect(body.error).toBe("upstream_unavailable");
      expect(body.message).toBe("Model catalog is temporarily unavailable. Try again shortly.");
      expect(JSON.stringify(body)).not.toContain("EAI_AGAIN");
      expect(errSpy).toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
      errSpy.mockRestore();
    }
  });
});
