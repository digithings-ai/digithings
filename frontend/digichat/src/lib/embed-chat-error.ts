/**
 * Map `/api/chat` failures to embed-friendly copy (REM-010) and BYOK suggestion policy.
 */

import type { EmbedLlmAccess } from "@/lib/embed-tenants";

/** Stable error codes digichat / digigraph may return on the embed chat path. */
export type EmbedChatErrorCode =
  | "embed_disabled"
  | "unauthorized"
  | "trial_gate"
  | "free_quota_exceeded"
  | "rate_limit"
  | "rate_limit_exceeded"
  | "byok_model_required"
  | string;

export type ParsedEmbedChatError = {
  code?: EmbedChatErrorCode;
  message?: string;
  raw: string;
};

/** Parse AI SDK / BFF error payloads (JSON body or plain text). */
export function parseEmbedChatError(error: Error | undefined): ParsedEmbedChatError | null {
  if (!error?.message) return null;
  const raw = error.message.trim();
  try {
    const parsed = JSON.parse(raw) as { error?: string; message?: string; code?: string };
    const code = parsed.error ?? parsed.code;
    return {
      code: typeof code === "string" ? code : undefined,
      message: typeof parsed.message === "string" ? parsed.message : undefined,
      raw,
    };
  } catch {
    if (raw.includes("free_quota_exceeded")) {
      return { code: "free_quota_exceeded", raw };
    }
    if (raw.includes("rate_limit_exceeded") || /\brate[_ ]?limit\b/i.test(raw)) {
      return { code: "rate_limit_exceeded", raw };
    }
    if (raw.includes("embed_disabled")) {
      return { code: "embed_disabled", raw };
    }
    if (raw.includes("unauthorized")) {
      return { code: "unauthorized", raw };
    }
    return { raw };
  }
}

/** True when the free path is exhausted or the provider rate-limited the free model. */
export function isFreeQuotaOrRateLimitError(code: string | undefined): boolean {
  if (!code) return false;
  return (
    code === "free_quota_exceeded" ||
    code === "rate_limit" ||
    code === "rate_limit_exceeded"
  );
}

/**
 * Whether embed should open / suggest the in-chat BYOK sequence for this error.
 *
 * Legacy (no `llmAccess`): ungated tenants suppress BYOK hints (dogfood used to
 * look "unlimited" and a key prompt felt wrong). With `llmAccess: free_then_byok`,
 * ungated + free quota exhaustion **does** suggest BYOK so digithings.ai can
 * hand off when OpenRouter `:free` is spent.
 */
export function shouldSuggestByokOnEmbedError(args: {
  llmAccess?: EmbedLlmAccess;
  showByok?: boolean;
  gateMode?: "turn_limited" | "ungated" | "trial_form";
  errorCode?: string;
}): boolean {
  const { llmAccess, showByok, gateMode, errorCode } = args;
  if (showByok === false) return false;
  if (llmAccess === "backend_only") return false;

  const quota = isFreeQuotaOrRateLimitError(errorCode);

  if (llmAccess === "free_then_byok") {
    return quota || errorCode === "byok_model_required";
  }
  if (llmAccess === "byok_only" || llmAccess === "operator") {
    return showByok === true && (quota || !!errorCode);
  }

  // Legacy: no llmAccess — ungated suppresses; gated + showByok suggests on quota.
  if (gateMode === "ungated") return false;
  if (showByok !== true) return false;
  return quota;
}

export function formatEmbedChatError(error: Error | undefined): string | null {
  const parsed = parseEmbedChatError(error);
  if (!parsed) return null;

  const { code, message, raw } = parsed;
  if (
    message &&
    (code === "embed_disabled" ||
      code === "unauthorized" ||
      code === "trial_gate" ||
      code === "free_quota_exceeded" ||
      code === "rate_limit" ||
      code === "rate_limit_exceeded")
  ) {
    return message;
  }
  if (code === "free_quota_exceeded" || raw.includes("free_quota_exceeded")) {
    return "Free tier quota is exhausted. Add your own API key to continue.";
  }
  if (code === "rate_limit" || code === "rate_limit_exceeded") {
    return message ?? "Rate limited. Try again shortly, or continue with your own API key.";
  }
  if (raw.includes("embed_disabled") || code === "embed_disabled") {
    return "Embed chat is not enabled on this host. Set DIGICHAT_EMBED_ENABLED=1 or configure X-Embed-Token.";
  }
  if (raw.includes("unauthorized") || code === "unauthorized") {
    return "Sign in on digithings.ai/chat or add your own API key below.";
  }
  return raw.length > 240 ? `${raw.slice(0, 240)}…` : raw;
}
