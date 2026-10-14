import { requireDigiChatAuth } from "@/lib/request-auth";
import {
  normalizeOpenRouterModel,
  OPENROUTER_API_BASE,
} from "@/lib/byok-openrouter";
import {
  byokKeyPrefixError,
  readByokProvider,
  type BYOKProvider,
} from "@/lib/byok-providers";
import {
  isEmbedChatRequest,
  resolveEmbedChatTenant,
} from "@/lib/embed-chat-tenant";
import { checkEmbedIpRateLimit } from "@/lib/embed-ip-rate-limit";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import { fetchWithTimeout, abortOrMessage } from "@/lib/fetch-with-timeout";
import { MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS } from "@/lib/model-catalog.generated";

export const maxDuration = 30;

type TestResult = {
  ok: boolean;
  model?: string;
  models?: { id: string; label: string }[];
  error?: string;
};

/**
 * The ids this provider's LiteLLM `model_name` groups can actually route.
 *
 * A provider's own `/models` endpoint lists everything the account can *see*,
 * which is routinely far more than the house can serve: Google's ListModels
 * returns 61 entries and `config/litellm.yaml` routes three. Every id outside
 * this set is a pick the proxy would refuse (`test_every_advertised_byok_preset_is_a_litellm_model_group`
 * #3605), and `config/litellm.yaml:6` routes strictly with no `fallbacks`, so
 * picking one is a hard failure rather than a degradation.
 *
 * The key-scoped list is what tells us the *key* works; this set is what tells
 * us the *model* is reachable. Both are needed, and they are independent: an
 * id can be live at the provider and unrouted here. The set is derived, not
 * declared — `scripts/refresh_model_catalog.py` reads it back out of the
 * litellm configs, so it cannot drift from them.
 */
function routableIds(provider: BYOKProvider): ReadonlySet<string> {
  return new Set(MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS[provider] ?? []);
}

/**
 * Narrow a provider's model list to the routable ids, preserving its order.
 *
 * Applied to the list *and* to the `model` default derived from it, because the
 * default is the other half of the bug: xAI lists `grok-4.20-*` first and Google
 * lists `gemini-2.5-flash` first, so an unfiltered `models[0]` names a model the
 * house cannot route even when every id in the list is routable. See #5000.
 */
function routableOnly(
  provider: BYOKProvider,
  models: { id: string; label: string }[],
): { id: string; label: string }[] {
  const routable = routableIds(provider);
  return models.filter((m) => routable.has(m.id));
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
  // A missing/empty header defaults to "openai" (unchanged behavior). A
  // *present but unrecognized* value is never silently coerced to "openai"
  // — it fails explicitly below instead (#2351).
  const rawProvider = req.headers.get("x-byok-provider")?.trim() ?? "";
  const provider = rawProvider === "" ? "openai" : readByokProvider(rawProvider);
  const byokModel = normalizeOpenRouterModel(
    req.headers.get("x-byok-model")?.trim() ?? ""
  );

  if (!byokKey) {
    return jsonResponse({ ok: false, error: "No BYOK key provided." }, 400);
  }

  if (provider === null) {
    return jsonResponse(
      { ok: false, error: `Unknown BYOK provider: "${rawProvider}".` },
      400
    );
  }

  const prefixError = byokKeyPrefixError(byokKey, provider);
  if (prefixError) {
    return jsonResponse({ ok: false, error: prefixError }, 400);
  }

  // Deliberately NOT derived from byokRequiresModel(provider) — that
  // predicate answers a different question (does /api/chat need a model
  // header). This gate answers only "does the *validation ping* need a
  // model before it can run at all" — and none of testOpenAIKey,
  // testAnthropicKey, testGeminiKey, or testOpenRouterKey read their model
  // parameter. Only testXaiKey has no live-list call of its own, so x.ai is
  // the one provider that still needs a model up front (#2347).
  const needsModel = provider === "xai";
  if (needsModel && !byokModel) {
    return jsonResponse(
      {
        ok: false,
        // The example must be a slug this provider serves. Correct by
        // construction only because the gate above is x.ai-only; if it ever
        // widens, derive the example per provider rather than hardcoding one
        // (#2537 fixed exactly this in digigraph, where a hardcoded
        // openai/… example was offered to four providers serving no such slug).
        error: `Model is required for ${provider} (e.g. grok-4.3).`,
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
    const models = routableOnly(
      "openai",
      (data.data ?? []).map((m) => ({ id: m.id, label: m.id })),
    );
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
    const models = routableOnly(
      "anthropic",
      (data.data ?? []).map((m) => ({ id: m.id, label: m.id })),
    );
    return { ok: true, model: models[0]?.id ?? "claude-haiku-4-5", models };
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
    const models = routableOnly(
      "gemini",
      (data.models ?? [])
        .map((m) => (m.name ?? "").replace(/^models\//, ""))
        .filter(Boolean)
        .map((id) => ({ id, label: id })),
    );
    // Fallback used only when the routable subset comes back empty (the key works
    // but none of the models the house routes are on this account). It has to be a
    // model that actually serves a fresh BYOK key: Google 404s `gemini-2.0-flash`
    // ("is no longer available.") and `gemini-2.5-flash-lite` alike ("no longer
    // available to new users"), so the old default handed back a model id that
    // could only fail. See #5000.
    return { ok: true, model: models[0]?.id ?? "gemini-3.5-flash-lite", models };
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
    // xAI's list is ordered `grok-4.20-*` first, none of which the house routes,
    // so an unfiltered `[0]` names a model the proxy refuses. Take the first
    // routable id instead. No `models[]` is returned: x.ai is not in
    // LIVE_PING_MODEL_PROVIDERS, so this result never drives the picker.
    const firstRoutable = (data.data ?? []).find((m) => routableIds("xai").has(m.id));
    return { ok: true, model: firstRoutable?.id ?? "grok-4.3" };
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
