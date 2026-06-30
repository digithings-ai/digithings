// Cloudflare Pages Function — POST /api/byok/test
// Validates a BYOK key against the selected provider (no persistence).

type ProviderId = "openrouter" | "openai" | "anthropic" | "gemini";

interface EventContext {
  request: Request;
}

type TestResult = { ok: boolean; model?: string; error?: string };

const TIMEOUT_MS = 10_000;

function jsonResponse(body: TestResult, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
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
  }
  return null;
}

async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
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
    return { ok: false, error: body.error?.message ?? `OpenRouter returned HTTP ${resp.status}` };
  }
  return { ok: true, model: "openai/gpt-4o-mini" };
}

async function testOpenAI(key: string): Promise<TestResult> {
  const resp = await fetchWithTimeout("https://api.openai.com/v1/models", {
    headers: { Authorization: `Bearer ${key}` },
  });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { error?: { message?: string } };
    return { ok: false, error: body.error?.message ?? `OpenAI returned HTTP ${resp.status}` };
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
    return { ok: false, error: body.error?.message ?? `Anthropic returned HTTP ${resp.status}` };
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
    return { ok: false, error: body.error?.message ?? `Gemini returned HTTP ${resp.status}` };
  }
  return { ok: true, model: "gemini-2.5-flash" };
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
  const raw = ctx.request.headers.get("x-byok-provider")?.trim() ?? "openrouter";
  const provider: ProviderId =
    raw === "openai" || raw === "anthropic" || raw === "gemini" || raw === "openrouter"
      ? raw
      : "openrouter";

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
    }
    return jsonResponse(result, result.ok ? 200 : 400);
  } catch (e) {
    return jsonResponse({ ok: false, error: abortMessage(e) }, 500);
  }
}
