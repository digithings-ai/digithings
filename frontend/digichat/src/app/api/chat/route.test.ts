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

vi.mock("@/lib/adapters/digithings/stream", () => ({
  createDigigraphTraceStreamResponse: vi.fn(async () => new Response("trace", { status: 200 })),
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
import { createDigigraphTraceStreamResponse } from "@/lib/adapters/digithings/stream";
import { resetEmbedTrialQuotaForTests } from "@/lib/embed-turn-quota";
import { resetChatRunLocksForTests } from "@/lib/chat-run-lock";
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
    resetChatRunLocksForTests();
    vi.mocked(createFoundryStreamResponse).mockClear();
    vi.mocked(createDigigraphTraceStreamResponse).mockClear();
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
    });
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

  it("forwards X-Digi-Force-Tool to digigraph upstream headers", async () => {
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
      })
    );
    expect(res.status).toBe(200);
    const call = vi.mocked(streamText).mock.calls.at(-1)?.[0] as {
      headers?: Record<string, string>;
    };
    expect(call?.headers?.["X-Digi-Force-Tool"]).toBe("digisearch");
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

  it("returns 409 run_in_progress for concurrent regen on the same session", async () => {
    vi.mocked(streamText).mockImplementationOnce(
      () =>
        ({
          toUIMessageStreamResponse: ({ headers }: { headers: Record<string, string> }) =>
            new Response(
              new ReadableStream({
                start() {
                  /* hold open until cancelled */
                },
              }),
              { status: 200, headers },
            ),
        }) as ReturnType<typeof streamText>,
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
    });
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
    });
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

  // #2351: byokNeedsModel is now byokRequiresModel(byokProvider) from the shared
  // frontend/digichat/src/lib/byok-providers.ts module instead of a hand-written
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
      // No embed config on an authenticated request, so the adapter gets the default.
      expect(call?.activityDetail).toBe("full");
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
  });
});
