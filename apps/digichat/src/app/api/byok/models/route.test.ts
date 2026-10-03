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
  checkEmbedIpRateLimit: vi.fn(() => ({ allowed: true })),
}));
vi.mock("@/lib/bff-rate-limit", () => ({
  checkBffRateLimit: vi.fn(() => ({ allowed: true })),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { resolveEmbedChatTenant } from "@/lib/embed-chat-tenant";
import { checkEmbedIpRateLimit } from "@/lib/embed-ip-rate-limit";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import { resetOpenRouterCatalogCache } from "@/lib/openrouter-catalog-cache";

function req(url: string, headers: Record<string, string> = {}) {
  return new Request(`http://localhost${url}`, { headers });
}

describe("GET /api/byok/models", () => {
  beforeEach(() => {
    resetOpenRouterCatalogCache();
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: true });
  });

  it("returns 401 without auth and not an embed request", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    const res = await GET(req("/api/byok/models?provider=openrouter"));
    expect(res.status).toBe(401);
  });

  it("returns 400 for a provider outside the BYOK allowlist", async () => {
    const res = await GET(req("/api/byok/models?provider=not-a-provider"));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBe("unsupported_provider");
  });

  it("serves every non-openrouter BYOK provider from the vendored catalog, without fetching", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    try {
      for (const provider of ["openai", "gemini", "xai"]) {
        const res = await GET(req(`/api/byok/models?provider=${provider}`));
        expect(res.status).toBe(200);
        const body = await res.json();
        expect(body.ok).toBe(true);
        expect(body.provider).toBe(provider);
        expect(body.source).toBe("catalog");
        expect(typeof body.fetchedAt).toBe("string");
        expect(Array.isArray(body.all)).toBe(true);
        // Not just `isArray` — an empty bucket array passes that trivially and
        // would let a broken catalogEntriesFor (or a stub that returned [])
        // satisfy this test. These providers each have routable ids the house
        // can actually serve, so the counts are the assertion that matters.
        expect(body.all.length).toBeGreaterThan(0);
      }
      // Spot-check one known routable id so a filter that returns the *wrong*
      // provider's rows still fails: xai's catalog carries grok-4.3 (dotted) and
      // the litellm route for it is grok-4-3 (dashed), so only grok-4.5 survives.
      const xai = await (await GET(req("/api/byok/models?provider=xai"))).json();
      expect(xai.all.map((m: { id: string }) => m.id)).toEqual(["grok-4.5"]);

      // anthropic is the deliberate empty case, and the empty result is the
      // finding: all three ids the house routes for anthropic are the pinned
      // claude-*-4-20250514 ids, which models.dev no longer carries, so none of
      // its 16 catalog rows is servable. The picker therefore falls back to
      // byokModelPresets for anthropic — correct, and asserted here so that a
      // future models.dev row for anthropic (or a new litellm route) shows up
      // as this count moving off zero.
      const anthropic = await (await GET(req("/api/byok/models?provider=anthropic"))).json();
      expect(anthropic.all).toEqual([]);
      // The catalog path is a local read: an upstream fetch here would mean this
      // route had become a fetch proxy for arbitrary provider hosts.
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("keeps openrouter on the live path", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ data: [{ id: "openai/gpt-4o-mini" }] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    try {
      const res = await GET(req("/api/byok/models?provider=openrouter"));
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.source).toBe("live");
      expect(body.provider).toBe("openrouter");
      expect(fetchSpy).toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
    }
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
    vi.mocked(checkEmbedIpRateLimit).mockReturnValue({ allowed: true });
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

  it("memoizes the bucketed catalog in-process (#2408)", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [{ id: "openai/gpt-oss-20b:free", pricing: { prompt: "0", completion: "0" } }] }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res1 = await GET(req("/api/byok/models?provider=openrouter"));
      const res2 = await GET(req("/api/byok/models?provider=openrouter"));
      expect(res1.status).toBe(200);
      expect(res2.status).toBe(200);
      expect(fetchSpy).toHaveBeenCalledTimes(1);
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
