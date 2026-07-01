import { createOpenAI } from "@ai-sdk/openai";

/**
 * OpenAI-compatible client pointed at DigiGraph (/v1).
 * @param baseUrlOverride — optional base without /v1 (from ecosystem cookie).
 * @param upstreamApiKeyOverride — DigiKey JWT or DIGIGRAPH_UPSTREAM_API_KEY (required).
 */
export function createDigiGraphClient(
  baseUrlOverride?: string | null,
  upstreamApiKeyOverride?: string | null
) {
  const base = (
    baseUrlOverride?.trim() ||
    process.env.DIGIGRAPH_INTERNAL_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
  const apiKey =
    (upstreamApiKeyOverride && upstreamApiKeyOverride.trim()) ||
    process.env.DIGIGRAPH_UPSTREAM_API_KEY?.trim();
  if (!apiKey) {
    throw new Error(
      "createDigiGraphClient: pass upstreamApiKeyOverride or set DIGIGRAPH_UPSTREAM_API_KEY"
    );
  }
  const openwebui = process.env.DIGICHAT_OPENWEBUI_FORMAT !== "0";

  return createOpenAI({
    name: "digigraph",
    baseURL: `${base}/v1`,
    apiKey,
    headers: openwebui ? { "X-Response-Format": "openwebui" } : undefined,
    fetch: async (url, init) => {
      if (!init?.body || typeof init.body !== "string") {
        return fetch(url, init);
      }
      try {
        const parsed = JSON.parse(init.body) as Record<string, unknown>;
        if (openwebui) {
          parsed.openwebui_format = true;
        }
        return fetch(url, { ...init, body: JSON.stringify(parsed) });
      } catch {
        return fetch(url, init);
      }
    },
  });
}

export function digigraphModelName() {
  return (process.env.DIGICHAT_MODEL ?? "sitaas-rag").trim() || "sitaas-rag";
}

export function digigraphChatCompletionsUrl(baseUrlOverride?: string | null) {
  const base = (
    baseUrlOverride?.trim() ||
    process.env.DIGIGRAPH_INTERNAL_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
  return `${base}/v1/chat/completions`;
}

/** @throws if unset (callers should use resolveDigigraphUpstreamBearer for JWT path). */
export function digigraphUpstreamApiKey() {
  const k = process.env.DIGIGRAPH_UPSTREAM_API_KEY?.trim();
  if (!k) {
    throw new Error("DIGIGRAPH_UPSTREAM_API_KEY is not set");
  }
  return k;
}

export function digigraphOpenWebUIFormat() {
  return process.env.DIGICHAT_OPENWEBUI_FORMAT !== "0";
}
