import { requireDigiChatAuth } from "@/lib/request-auth";

export const maxDuration = 30;

const TIMEOUT_MS = 10_000;

type TestResult = { ok: boolean; model?: string; error?: string };

export async function POST(req: Request): Promise<Response> {
  const authResult = await requireDigiChatAuth(req);
  if (authResult instanceof Response) return authResult;

  const byokKey = req.headers.get("x-byok-key")?.trim() ?? "";
  const provider = (req.headers.get("x-byok-provider")?.trim() ?? "openai") as
    | "openai"
    | "anthropic";

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

  try {
    const result = await testKey(byokKey, provider);
    return jsonResponse(result, result.ok ? 200 : 400);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Unexpected error";
    return jsonResponse({ ok: false, error: msg }, 500);
  }
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit
): Promise<globalThis.Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

function abortOrMessage(e: unknown): string {
  if (e instanceof Error) {
    return e.name === "AbortError" ? `Request timed out after ${TIMEOUT_MS / 1000} s.` : e.message;
  }
  return "Unknown error";
}

async function testKey(
  key: string,
  provider: "openai" | "anthropic"
): Promise<TestResult> {
  if (provider === "openai") {
    return testOpenAIKey(key);
  }
  return testAnthropicKey(key);
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
    return { ok: true, model: data.data?.[0]?.id ?? "gpt-4o-mini" };
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
    return { ok: true, model: data.data?.[0]?.id ?? "claude-3-haiku-20240307" };
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
