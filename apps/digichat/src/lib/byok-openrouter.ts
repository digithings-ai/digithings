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
