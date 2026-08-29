import { requireDigiChatAuth } from "@/lib/request-auth";
import { isEmbedChatRequest, resolveEmbedChatTenant } from "@/lib/embed-chat-tenant";
import { checkEmbedIpRateLimit } from "@/lib/embed-ip-rate-limit";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import { fetchWithTimeout, abortOrMessage } from "@/lib/fetch-with-timeout";
import { OPENROUTER_API_BASE } from "@/lib/byok-openrouter";
import { bucketOpenRouterModels, type OpenRouterCatalogEntry } from "@/lib/openrouter-catalog";

export const maxDuration = 15;

/** Reject a response body larger than this — see the design spec's Error handling
 * section on unbounded response size.
 *
 * Two checks, and only the first avoids buffering: content-length is consulted
 * before reading the body, but OpenRouter may respond chunked, in which case the
 * header is absent and the second check runs only after resp.text() has already
 * buffered everything. Acceptable here because the origin is a single fixed TLS
 * endpoint, not attacker-chosen. Note the post-buffer check counts UTF-16 code
 * units, so it admits up to 3x this many bytes: a character in U+0800–U+FFFF is
 * one UTF-16 code unit but three UTF-8 bytes. (Astral characters are the milder
 * 2x case — four bytes across two code units.) */
const MAX_RESPONSE_BYTES = 2_000_000; // 2 MB

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/**
 * GET /api/byok/models — live OpenRouter model catalog for the BYOK picker's tier
 * tabs. OpenRouter's `/models` listing is public (no key needed or forwarded);
 * `provider` is restricted to `openrouter` only — 400 for anything else, so a
 * naive `catalog[provider].baseUrl` mistake can never turn this into an
 * unauthenticated fetch proxy for the other four BYOK providers.
 *
 * Rate-limited on BOTH the embed-IP path AND the authenticated/session path
 * (same shape as /api/byok/test) — this route needs no key at all to
 * trigger, a lower bar than /api/byok/test.
 */
export async function GET(req: Request): Promise<Response> {
  const authResult = await requireDigiChatAuth(req);
  let rateKey: string;
  if (authResult instanceof Response) {
    if (!isEmbedChatRequest(req)) return authResult;
    const embedCtx = resolveEmbedChatTenant(req);
    if (embedCtx instanceof Response) return embedCtx;
    const ipRate = checkEmbedIpRateLimit(req);
    if (!ipRate.allowed) {
      return jsonResponse(
        { error: "rate_limited", message: "Too many requests from this address. Try again shortly." },
        429,
      );
    }
    rateKey = `byok-models:embed:${embedCtx.tenantSlug}`;
  } else {
    rateKey = `byok-models:${authResult.tenantSlug}:${authResult.ownerUserSub}`;
  }

  const rate = checkBffRateLimit(rateKey);
  if (!rate.allowed) {
    return jsonResponse({ error: "rate_limited", message: "Too many requests. Try again shortly." }, 429);
  }

  const provider = (new URL(req.url).searchParams.get("provider") || "").trim().toLowerCase();
  if (provider !== "openrouter") {
    return jsonResponse(
      { error: "unsupported_provider", message: "Only provider=openrouter is supported." },
      400,
    );
  }

  try {
    const resp = await fetchWithTimeout(`${OPENROUTER_API_BASE}/models`, { method: "GET" });
    if (!resp.ok) {
      return jsonResponse({ error: "upstream_error", message: `OpenRouter returned HTTP ${resp.status}` }, 502);
    }
    const contentLength = Number(resp.headers.get("content-length") ?? "0");
    if (contentLength > MAX_RESPONSE_BYTES) {
      return jsonResponse({ error: "response_too_large" }, 502);
    }
    const text = await resp.text();
    if (text.length > MAX_RESPONSE_BYTES) {
      return jsonResponse({ error: "response_too_large" }, 502);
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      return jsonResponse({ error: "malformed_response" }, 502);
    }
    const data = (parsed as { data?: unknown }).data;
    if (!Array.isArray(data)) {
      return jsonResponse({ error: "malformed_response" }, 502);
    }
    const buckets = bucketOpenRouterModels(data as OpenRouterCatalogEntry[]);
    return jsonResponse({ ok: true, ...buckets }, 200);
  } catch (e) {
    return jsonResponse({ ok: false, error: abortOrMessage(e) }, 502);
  }
}
