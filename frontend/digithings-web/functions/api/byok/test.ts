// Cloudflare Pages Function — POST /api/byok/test
// Validates a BYOK key against the selected provider (no persistence).

type ProviderId = "openrouter" | "openai" | "anthropic" | "gemini" | "xai";

interface EventContext {
  request: Request;
}

type TestResult = { ok: boolean; model?: string; error?: string };

const TIMEOUT_MS = 10_000;
// Defensive cap on upstream provider error text passed through to the client
// (see `sanitizeUpstreamError` below) -- not a UX limit, just a ceiling.
const MAX_UPSTREAM_ERROR_LEN = 300;

function jsonResponse(body: TestResult, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      // Responses here can carry information derived from a submitted secret
      // key (validation result, provider error text) -- never cache.
      "cache-control": "no-store",
    },
  });
}

function validateKey(key: string, provider: ProviderId): string | null {
  if (!key) return "API key is required.";
  switch (provider) {
    case "openrouter":
      if (!key.startsWith("sk-or-")) return "OpenRouter keys start with sk-or-.";
      break;
    case "openai":
      if (!key.startsWith("sk-")) return "OpenAI keys start with sk-.";
      break;
    case "anthropic":
      if (!key.startsWith("sk-ant-")) return "Anthropic keys start with sk-ant-.";
      break;
    case "gemini":
      if (!key.startsWith("AI")) return "Gemini keys start with AI.";
      break;
    case "xai":
      if (!key.startsWith("xai-")) return "x.ai keys start with xai-.";
      break;
    default: {
      const _exhaustive: never = provider;
      return _exhaustive;
    }
  }
  return null;
}

/**
 * Upstream provider error bodies are passed through to the client today
 * (`testOpenRouter` and its siblings return `body.error?.message` verbatim).
 * Defense in depth in case a provider ever echoes the submitted key back in
 * an error: strip any occurrence of the raw key and cap the length so a
 * pathological upstream response can't balloon the reply either.
 *
 * Callers must combine this with `||`, never `??`. It returns `""` unchanged
 * for an empty message — `""` is not nullish, so `??` keeps it and ships
 * `{"ok":false,"error":""}` instead of falling back to the HTTP-status text.
 */
function sanitizeUpstreamError(message: string | undefined, key: string): string | undefined {
  if (!message) return message;
  // Redact the percent-encoded form too. Gemini's key rides in the request URL
  // via encodeURIComponent, so an error quoting that URL echoes the encoded key,
  // which a literal split(key) would miss. encodeURIComponent is the identity for
  // a canonical `AIza…[A-Za-z0-9_-]{35}` key — this covers the non-canonical ones
  // validateKey's `startsWith("AI")` check still lets through.
  let sanitized = message;
  for (const form of new Set([key, encodeURIComponent(key)])) {
    if (form) sanitized = sanitized.split(form).join("[redacted]");
  }
  if (sanitized.length > MAX_UPSTREAM_ERROR_LEN) {
    sanitized = `${sanitized.slice(0, MAX_UPSTREAM_ERROR_LEN)}…`;
  }
  return sanitized;
}

async function fetchWithTimeout(url: string, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function abortMessage(e: unknown): string {
  if (e instanceof Error) {
    return e.name === "AbortError" ? `Request timed out after ${TIMEOUT_MS / 1000} s.` : e.message;
  }
  return "Unknown error";
}

async function testOpenRouter(key: string): Promise<TestResult> {
  const resp = await fetchWithTimeout("https://openrouter.ai/api/v1/models", {
    headers: { Authorization: `Bearer ${key}` },
  });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { error?: { message?: string } };
    return {
      ok: false,
      error:
        sanitizeUpstreamError(body.error?.message, key) ||
        `OpenRouter returned HTTP ${resp.status}`,
    };
  }
  return { ok: true, model: "openai/gpt-4o-mini" };
}

async function testOpenAI(key: string): Promise<TestResult> {
  const resp = await fetchWithTimeout("https://api.openai.com/v1/models", {
    headers: { Authorization: `Bearer ${key}` },
  });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { error?: { message?: string } };
    return {
      ok: false,
      error: sanitizeUpstreamError(body.error?.message, key) || `OpenAI returned HTTP ${resp.status}`,
    };
  }
  const data = (await resp.json()) as { data?: { id: string }[] };
  return { ok: true, model: data.data?.[0]?.id ?? "gpt-4o-mini" };
}

async function testAnthropic(key: string): Promise<TestResult> {
  const resp = await fetchWithTimeout("https://api.anthropic.com/v1/models", {
    headers: { "x-api-key": key, "anthropic-version": "2023-06-01" },
  });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { error?: { message?: string } };
    return {
      ok: false,
      error:
        sanitizeUpstreamError(body.error?.message, key) || `Anthropic returned HTTP ${resp.status}`,
    };
  }
  const data = (await resp.json()) as { data?: { id: string }[] };
  return { ok: true, model: data.data?.[0]?.id ?? "claude-3-5-haiku-20241022" };
}

async function testGemini(key: string): Promise<TestResult> {
  const resp = await fetchWithTimeout(
    `https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(key)}`,
  );
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { error?: { message?: string } };
    return {
      ok: false,
      error: sanitizeUpstreamError(body.error?.message, key) || `Gemini returned HTTP ${resp.status}`,
    };
  }
  return { ok: true, model: "gemini-2.5-flash" };
}

async function testXai(key: string): Promise<TestResult> {
  const resp = await fetchWithTimeout("https://api.x.ai/v1/models", {
    headers: { Authorization: `Bearer ${key}` },
  });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { error?: { message?: string } };
    return {
      ok: false,
      error: sanitizeUpstreamError(body.error?.message, key) || `x.ai returned HTTP ${resp.status}`,
    };
  }
  const data = (await resp.json()) as { data?: { id: string }[] };
  return { ok: true, model: data.data?.[0]?.id ?? "grok-4-3" };
}

function sameSiteOK(request: Request): boolean {
  const reqHost = new URL(request.url).hostname;
  if (reqHost === "localhost" || reqHost === "127.0.0.1") return true;
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).hostname === reqHost;
  } catch {
    return false;
  }
}

export async function onRequestPost(ctx: EventContext): Promise<Response> {
  if (!sameSiteOK(ctx.request)) {
    return jsonResponse({ ok: false, error: "Cross-site requests are not allowed." }, 403);
  }

  const key = ctx.request.headers.get("x-byok-key")?.trim() ?? "";
  // No provider header at all defaults to openrouter (back-compat for callers
  // that don't set it). A header that IS present but names something we don't
  // recognize is a genuine client error, not something to paper over — silently
  // coercing it to openrouter would run a stranger's key against the wrong
  // provider's API and surface a confusing OpenRouter-flavored error.
  const rawHeader = ctx.request.headers.get("x-byok-provider")?.trim() ?? "";
  const raw = rawHeader || "openrouter";
  if (
    raw !== "openai" &&
    raw !== "anthropic" &&
    raw !== "gemini" &&
    raw !== "openrouter" &&
    raw !== "xai"
  ) {
    return jsonResponse({ ok: false, error: `Unknown BYOK provider: ${raw}` }, 400);
  }
  const provider: ProviderId = raw;

  const validation = validateKey(key, provider);
  if (validation) return jsonResponse({ ok: false, error: validation }, 400);

  try {
    let result: TestResult;
    switch (provider) {
      case "openrouter":
        result = await testOpenRouter(key);
        break;
      case "openai":
        result = await testOpenAI(key);
        break;
      case "anthropic":
        result = await testAnthropic(key);
        break;
      case "gemini":
        result = await testGemini(key);
        break;
      case "xai":
        result = await testXai(key);
        break;
    }
    return jsonResponse(result, result.ok ? 200 : 400);
  } catch (e) {
    // Sanitize here too, not just on the upstream-error paths. A fetch/network
    // failure message can quote the request URL, and Gemini's key rides in that
    // URL (`...models?key=`), so an unsanitized `e.message` echoes the caller's
    // key straight back in a 500 body.
    // `||`, not `??`: sanitizeUpstreamError("") returns "" — not nullish — so `??`
    // would ship `{"ok":false,"error":""}` whenever e.message is empty.
    const detail = sanitizeUpstreamError(abortMessage(e), key) || "Request failed";
    return jsonResponse({ ok: false, error: detail }, 500);
  }
}
