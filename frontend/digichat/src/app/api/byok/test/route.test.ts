import { readFileSync } from "node:fs";
import { join } from "node:path";
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

vi.mock("@/lib/bff-rate-limit", () => ({
  checkBffRateLimit: vi.fn(() => ({ allowed: true })),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { resolveEmbedChatTenant } from "@/lib/embed-chat-tenant";
import { checkEmbedIpRateLimit } from "@/lib/embed-ip-rate-limit";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";

describe("POST /api/byok/test", () => {
  beforeEach(() => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(checkEmbedIpRateLimit).mockReturnValue({
      allowed: true,
      retryAfterSec: 0,
    });
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: true });
  });

  // Fix 5 regression: the authenticated path previously had no rate limit at
  // all here (unlike GET /api/byok/models, which checkBffRateLimit-gates both
  // paths) — an authenticated caller could loop this route and spend
  // digichat's own egress against a third-party provider with no ceiling.
  it("rate-limits authenticated callers, not just embed (isolated from the embed-IP check)", async () => {
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: false, retryAfterSec: 5 });
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: { "x-byok-key": "sk-test", "x-byok-provider": "openai" },
      }),
    );
    expect(res.status).toBe(429);
    expect(checkBffRateLimit).toHaveBeenCalled();
    // Never reached the embed-IP check — this is the authenticated path.
    expect(checkEmbedIpRateLimit).not.toHaveBeenCalled();
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
    expect(res.status).toBe(429);
    expect(checkBffRateLimit).toHaveBeenCalled();
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

  // #2351: readProvider used to fall through to "openai" for any unrecognized
  // x-byok-provider value. readByokProvider (from the shared
  // frontend/digichat/src/lib/byok-providers.ts module) never coerces —
  // an unrecognized value must fail explicitly instead of silently being
  // validated as OpenAI.
  it("returns 400 with an explicit unknown-provider error for an unrecognized provider, instead of silently validating as OpenAI", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: { "x-byok-key": "sk-test", "x-byok-provider": "bogus" },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.ok).toBe(false);
    expect(body.error).toMatch(/unknown/i);
    expect(body.error).toContain("bogus");
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
        headers: { "x-byok-key": "sk-proj-bad", "x-byok-provider": "openrouter" },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("sk-or-");
  });

  it("validates an OpenRouter key via GET /api/v1/key with no model required", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: { label: "test-key", limit: 10, usage: 1, is_free_tier: false } }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: { "x-byok-key": "sk-or-v1-test", "x-byok-provider": "openrouter" },
        }),
      );
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.ok).toBe(true);
      const [url] = fetchSpy.mock.calls[0] as [string];
      expect(url).toBe("https://openrouter.ai/api/v1/key");
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("rejects an OpenRouter key with zero remaining credit even on HTTP 200", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: { label: "exhausted", limit: 10, usage: 10, is_free_tier: false } }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: { "x-byok-key": "sk-or-v1-test", "x-byok-provider": "openrouter" },
        }),
      );
      expect(res.status).toBe(400);
      const body = await res.json();
      expect(body.ok).toBe(false);
      expect(body.error).toContain("credit");
    } finally {
      fetchSpy.mockRestore();
    }
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

  // #2347: testGeminiKey never reads its `model` parameter — requiring one
  // before the ping just delayed a call that would have worked without it.
  it("no longer requires a model for Gemini (Gemini's own call never reads it)", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ models: [{ name: "models/gemini-2.0-flash" }] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: {
            "x-byok-key": "AIza-test",
            "x-byok-provider": "gemini",
          },
        }),
      );
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.ok).toBe(true);
    } finally {
      fetchSpy.mockRestore();
    }
  });

  // #2347: same reasoning as the Gemini case above — testAnthropicKey never
  // reads its `model` parameter either.
  it("no longer requires a model for Anthropic (Anthropic's own call never reads it)", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: [{ id: "claude-3-5-haiku-20241022" }] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: {
            "x-byok-key": "sk-ant-test",
            "x-byok-provider": "anthropic",
          },
        }),
      );
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.ok).toBe(true);
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("returns 400 for invalid x.ai key prefix", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: {
          "x-byok-key": "not-xai",
          "x-byok-provider": "xai",
          "x-byok-model": "grok-4-3",
        },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("xai-");
  });

  it("returns 400 when x.ai model header missing", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: {
          "x-byok-key": "xai-test",
          "x-byok-provider": "xai",
        },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("Model is required");
    // `toContain("Model is required")` alone is why a wrong example survived
    // here: the branch is x.ai-only, yet the message named `openai/gpt-4o-mini`,
    // a slug x.ai serves none of — so it was wrong 100% of the times it showed.
    // Pin the example to x.ai's own catalog entry, not just the sentence.
    const example = /\(e\.g\. (.+?)\)/.exec(body.error as string)?.[1];
    expect(example).toBeTruthy();
    const catalog = JSON.parse(
      readFileSync(join(__dirname, "../../../../../../../config/byok-providers.json"), "utf-8")
    ) as { id: string; fallbackModels?: string[] }[];
    const xaiModels = catalog.find((e) => e.id === "xai")?.fallbackModels ?? [];
    expect(xaiModels.length).toBeGreaterThan(0);
    expect(xaiModels).toContain(example);
  });

  it("returns the full model list for a valid OpenAI key, not just the first id", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [{ id: "gpt-4o-mini" }, { id: "gpt-4o" }, { id: "o4-mini" }] }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: { "x-byok-key": "sk-test", "x-byok-provider": "openai" },
        }),
      );
      const body = await res.json();
      expect(body.models).toEqual([
        { id: "gpt-4o-mini", label: "gpt-4o-mini" },
        { id: "gpt-4o", label: "gpt-4o" },
        { id: "o4-mini", label: "o4-mini" },
      ]);
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("returns the full model list for a valid Gemini key, from the models[].name shape", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          models: [{ name: "models/gemini-2.0-flash" }, { name: "models/gemini-2.5-flash" }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: {
            "x-byok-key": "AIza-test",
            "x-byok-provider": "gemini",
            "x-byok-model": "gemini/gemini-2.0-flash",
          },
        }),
      );
      const body = await res.json();
      expect(body.models).toEqual([
        { id: "gemini-2.0-flash", label: "gemini-2.0-flash" },
        { id: "gemini-2.5-flash", label: "gemini-2.5-flash" },
      ]);
    } finally {
      fetchSpy.mockRestore();
    }
  });
});
