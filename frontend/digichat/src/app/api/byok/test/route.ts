import { requireDigiChatAuth } from "@/lib/request-auth";
import {
  isOpenRouterKey,
  normalizeOpenRouterModel,
  OPENROUTER_API_BASE,
} from "@/lib/byok-openrouter";
import {
  isEmbedChatRequest,
  resolveEmbedChatTenant,
} from "@/lib/embed-chat-tenant";
import { checkEmbedIpRateLimit } from "@/lib/embed-ip-rate-limit";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import { fetchWithTimeout, abortOrMessage } from "@/lib/fetch-with-timeout";

export const maxDuration = 30;

type TestResult = {
  ok: boolean;
  model?: string;
  models?: { id: string; label: string }[];
  error?: string;
};

type BYOKProvider = "openai" | "anthropic" | "openrouter" | "gemini" | "xai";

function readProvider(raw: string): BYOKProvider {
  if (raw === "anthropic") return "anthropic";
  if (raw === "openrouter") return "openrouter";
  if (raw === "gemini") return "gemini";
  if (raw === "xai") return "xai";
  return "openai";
}

function rateLimitResponse(message: string, retryAfterSec: number): Response {
  return new Response(JSON.stringify({ ok: false, error: message }), {
    status: 429,
    headers: {
      "content-type": "application/json",
      "retry-after": String(retryAfterSec),
    },
  });
}

/**
 * POST /api/byok/test — ping a visitor BYOK key against the provider.
 *
 * The raw key is read from `X-BYOK-Key` for this request only. It is never
 * logged, never written to disk/DB, and never echoed in the JSON body.
 *
 * Auth mirrors POST /api/chat: DigiChat session/machine key, OR a verified
 * anonymous embed request (`X-Embed-Host` / embed referer). Embed visitors on
 * digithings.ai / OCC must validate BYOK before session activation.
 *
 * Rate-limited on BOTH the embed-IP path AND the authenticated/session path —
 * same unconditional-on-both-paths shape as GET /api/byok/models. Each call
 * here makes an outbound credentialed request to a third-party provider using
 * digichat's own egress, so an authenticated caller looping this route
 * unthrottled was a real gap (unlike /api/byok/models, this route needs a key
 * to do anything, but the egress cost is per-request regardless of whether
 * the key turns out to be valid).
 */
export async function POST(req: Request): Promise<Response> {
  const authResult = await requireDigiChatAuth(req);
  let rateKey: string;
  if (authResult instanceof Response) {
    if (!isEmbedChatRequest(req)) return authResult;
    const embedCtx = resolveEmbedChatTenant(req);
    if (embedCtx instanceof Response) return embedCtx;
    const ipRate = checkEmbedIpRateLimit(req);
    if (!ipRate.allowed) {
      return rateLimitResponse(
        "Too many requests from this address. Try again shortly.",
        ipRate.retryAfterSec,
      );
    }
    rateKey = `byok-test:embed:${embedCtx.tenantSlug}`;
  } else {
    rateKey = `byok-test:${authResult.tenantSlug}:${authResult.ownerUserSub}`;
  }

  const rate = checkBffRateLimit(rateKey);
  if (!rate.allowed) {
    return rateLimitResponse("Too many requests. Try again shortly.", rate.retryAfterSec);
  }

  const byokKey = req.headers.get("x-byok-key")?.trim() ?? "";
  const provider = readProvider(req.headers.get("x-byok-provider")?.trim() ?? "openai");
  const byokModel = normalizeOpenRouterModel(
    req.headers.get("x-byok-model")?.trim() ?? ""
  );

  if (!byokKey) {
    return jsonResponse({ ok: false, error: "No BYOK key provided." }, 400);
  }

  if (provider === "openai" && !byokKey.startsWith("sk-")) {
    return jsonResponse(
      { ok: false, error: "OpenAI keys must start with sk-." },
      400
    );
  }
  if (provider === "anthropic" && !byokKey.startsWith("sk-ant-")) {
    return jsonResponse(
      { ok: false, error: "Anthropic keys must start with sk-ant-." },
      400
    );
  }
  if (provider === "openrouter" && !isOpenRouterKey(byokKey)) {
    return jsonResponse(
      { ok: false, error: "OpenRouter keys must start with sk-or-." },
      400
    );
  }
  if (provider === "gemini" && !byokKey.startsWith("AI")) {
    return jsonResponse(
      { ok: false, error: "Gemini keys must start with AI." },
      400
    );
  }
  if (provider === "xai" && !byokKey.startsWith("xai-")) {
    return jsonResponse({ ok: false, error: "x.ai keys must start with xai-." }, 400);
  }

  const needsModel =
    provider === "anthropic" || provider === "gemini" || provider === "xai";
  if (needsModel && !byokModel) {
    return jsonResponse(
      {
        ok: false,
        error: `Model is required for ${provider} (e.g. openai/gpt-4o-mini).`,
      },
      400
    );
  }

  try {
    const result = await testKey(byokKey, provider, byokModel);
    return jsonResponse(result, result.ok ? 200 : 400);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Unexpected error";
    return jsonResponse({ ok: false, error: msg }, 500);
  }
}

async function testKey(
  key: string,
  provider: BYOKProvider,
  model: string
): Promise<TestResult> {
  switch (provider) {
    case "openai":
      return testOpenAIKey(key);
    case "anthropic":
      return testAnthropicKey(key);
    case "openrouter":
      return testOpenRouterKey(key);
    case "gemini":
      return testGeminiKey(key);
    case "xai":
      return testXaiKey(key);
    default: {
      const _exhaustive: never = provider;
      return _exhaustive;
    }
  }
}

async function testOpenAIKey(key: string): Promise<TestResult> {
  try {
    const resp = await fetchWithTimeout("https://api.openai.com/v1/models", {
      headers: { Authorization: `Bearer ${key}` },
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => ({}))) as {
        error?: { message?: string };
      };
      return { ok: false, error: body.error?.message ?? `OpenAI returned HTTP ${resp.status}` };
    }
    const data = (await resp.json()) as { data?: { id: string }[] };
    const models = (data.data ?? []).map((m) => ({ id: m.id, label: m.id }));
    return { ok: true, model: models[0]?.id ?? "gpt-4o-mini", models };
  } catch (e) {
    return { ok: false, error: abortOrMessage(e) };
  }
}

async function testAnthropicKey(key: string): Promise<TestResult> {
  try {
    const resp = await fetchWithTimeout("https://api.anthropic.com/v1/models", {
      headers: {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
      },
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => ({}))) as {
        error?: { message?: string };
      };
      return { ok: false, error: body.error?.message ?? `Anthropic returned HTTP ${resp.status}` };
    }
    const data = (await resp.json()) as { data?: { id: string }[] };
    const models = (data.data ?? []).map((m) => ({ id: m.id, label: m.id }));
    return { ok: true, model: models[0]?.id ?? "claude-3-haiku-20240307", models };
  } catch (e) {
    return { ok: false, error: abortOrMessage(e) };
  }
}

async function testOpenRouterKey(key: string): Promise<TestResult> {
  try {
    const resp = await fetchWithTimeout(`${OPENROUTER_API_BASE}/key`, {
      headers: { Authorization: `Bearer ${key}` },
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => ({}))) as {
        error?: { message?: string };
      };
      return {
        ok: false,
        error: body.error?.message ?? `OpenRouter returned HTTP ${resp.status}`,
      };
    }
    const data = (await resp.json()) as {
      data?: { limit?: number | null; usage?: number };
    };
    const limit = data.data?.limit;
    const usage = data.data?.usage ?? 0;
    // limit === null means unlimited/no cap on this key — only a finite,
    // fully-consumed limit means "this key has no credit left."
    if (typeof limit === "number" && usage >= limit) {
      return { ok: false, error: "This OpenRouter key has no remaining credit." };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: abortOrMessage(e) };
  }
}

async function testGeminiKey(key: string): Promise<TestResult> {
  try {
    // Prefer header auth — query-string `?key=` can land in egress/proxy/URL logs.
    // https://ai.google.dev/api (x-goog-api-key)
    const resp = await fetchWithTimeout(
      "https://generativelanguage.googleapis.com/v1beta/models",
      { method: "GET", headers: { "x-goog-api-key": key } },
    );
    if (!resp.ok) {
      const body = (await resp.json().catch(() => ({}))) as {
        error?: { message?: string };
      };
      return {
        ok: false,
        error: body.error?.message ?? `Gemini returned HTTP ${resp.status}`,
      };
    }
    const data = (await resp.json()) as { models?: { name?: string }[] };
    const models = (data.models ?? [])
      .map((m) => (m.name ?? "").replace(/^models\//, ""))
      .filter(Boolean)
      .map((id) => ({ id, label: id }));
    return { ok: true, model: models[0]?.id ?? "gemini-2.0-flash", models };
  } catch (e) {
    return { ok: false, error: abortOrMessage(e) };
  }
}

async function testXaiKey(key: string): Promise<TestResult> {
  try {
    const resp = await fetchWithTimeout("https://api.x.ai/v1/models", {
      headers: { Authorization: `Bearer ${key}` },
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => ({}))) as {
        error?: { message?: string };
      };
      return { ok: false, error: body.error?.message ?? `x.ai returned HTTP ${resp.status}` };
    }
    const data = (await resp.json()) as { data?: { id: string }[] };
    return { ok: true, model: data.data?.[0]?.id ?? "grok-4-3" };
  } catch (e) {
    return { ok: false, error: abortOrMessage(e) };
  }
}

function jsonResponse(body: TestResult, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
