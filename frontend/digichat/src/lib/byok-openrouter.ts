import { createOpenAI } from "@ai-sdk/openai";

export const OPENROUTER_API_BASE = "https://openrouter.ai/api/v1";

/** OpenRouter keys are issued as `sk-or-v1-…` (or legacy `sk-or-…`). */
export function isOpenRouterKey(key: string): boolean {
  return key.startsWith("sk-or-");
}

/** Normalize user input to an OpenRouter model slug (`provider/model`). */
export function normalizeOpenRouterModel(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("openrouter/")) {
    return trimmed.slice("openrouter/".length);
  }
  return trimmed;
}

export function createOpenRouterByokProvider(apiKey: string) {
  const referer =
    process.env.DIGICHAT_SITE_URL?.trim() || "https://chat.digithings.ai";
  return createOpenAI({
    name: "openrouter-byok",
    baseURL: OPENROUTER_API_BASE,
    apiKey,
    headers: {
      "HTTP-Referer": referer,
      "X-OpenRouter-Title": "DigiChat",
    },
  });
}
