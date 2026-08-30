/**
 * Map `/api/chat` failures to embed-friendly copy (REM-010) and BYOK suggestion policy.
 */

import { LEGACY_EMBED_DISABLED_MESSAGE } from "@/lib/embed-legacy-gate";
import type { EmbedLlmAccess } from "@/lib/embed-tenants";

const NETWORK_ERROR_RE =
  /\b(fetch failed|failed to fetch|networkerror|network error|econnrefused)\b/i;

const UPSTREAM_ERROR_CODES = new Set([
  "upstream_auth",
  "upstream_auth_failed",
  "service_unavailable",
]);

/** Stable error codes digichat / digigraph may return on the embed chat path. */
export type EmbedChatErrorCode =
  | "embed_disabled"
  | "unauthorized"
  | "trial_gate"
  | "free_quota_exceeded"
  | "rate_limit"
  | "rate_limit_exceeded"
  | "byok_model_required"
  | "byok_default_model_provider_mismatch"
  | string;

/**
 * digigraph refusals a user fixes by naming a model, not by waiting or signing in.
 *
 * `byok_model_required` is a property of the provider — digichat's own catalog knows
 * it. `byok_default_model_provider_mismatch` is a property of the *digigraph
 * deployment*: its default model is served by another provider, so a bound key with
 * no model would be accepted and never spent (#2490). The frontend cannot predict
 * that one, so it can only react to it — and the reaction is identical: open the
 * BYOK sequence so the user can pick a model.
 */
export const BYOK_MODEL_REMEDIABLE_CODES: ReadonlySet<string> = new Set([
  "byok_model_required",
  "byok_default_model_provider_mismatch",
]);

/**
 * Copy for a model-remediable refusal that arrives as a bare code.
 *
 * The embed transport relays the code without digigraph's message on purpose: a
 * digigraph 400 body is not written for anonymous embed visitors, and
 * `byok_default_model_provider_mismatch`'s message reflects the caller's own
 * `X-BYOK-Provider` header back at them. Copy lives here instead.
 */
export const BYOK_MODEL_REMEDIABLE_MESSAGE =
  "Your API key needs a model. Update your key below and choose a model for your provider.";

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

function isInfraEmbedFailure(errorCode?: string, errorMessage?: string | null): boolean {
  if (errorCode && UPSTREAM_ERROR_CODES.has(errorCode)) return true;
  if (!errorMessage) return false;
  const lower = errorMessage.toLowerCase();
  if (NETWORK_ERROR_RE.test(lower)) return true;
  if (lower.includes("digigraph") || lower.includes("digikey") || lower.includes("upstream")) {
    return true;
  }
  if (lower.includes("make stack-local") || lower.includes("make digichat-dev")) {
    return true;
  }
  return false;
}

/**
 * Whether embed should open / suggest the in-chat BYOK sequence for this error.
 *
 * Legacy (no `llmAccess`): ungated tenants suppress BYOK hints (dogfood used to
 * look "unlimited" and a key prompt felt wrong). With `llmAccess: free_then_byok`,
 * ungated + free quota exhaustion **does** suggest BYOK so digithings.ai can
 * hand off when OpenRouter `:free` is spent.
 *
 * Network / upstream infra failures never suggest BYOK (stack is down, not quota).
 */
export function shouldSuggestByokOnEmbedError(args: {
  llmAccess?: EmbedLlmAccess;
  showByok?: boolean;
  gateMode?: "turn_limited" | "ungated" | "trial_form";
  errorCode?: string;
  errorMessage?: string | null;
}): boolean {
  const { llmAccess, showByok, gateMode, errorCode, errorMessage } = args;
  if (showByok === false) return false;
  if (llmAccess === "backend_only") return false;
  if (isInfraEmbedFailure(errorCode, errorMessage)) return false;

  const quota = isFreeQuotaOrRateLimitError(errorCode);

  if (llmAccess === "free_then_byok") {
    return quota || (!!errorCode && BYOK_MODEL_REMEDIABLE_CODES.has(errorCode));
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
      code === "rate_limit_exceeded" ||
      (code != null && UPSTREAM_ERROR_CODES.has(code)) ||
      (code != null && BYOK_MODEL_REMEDIABLE_CODES.has(code)))
  ) {
    return message;
  }
  if (code === "free_quota_exceeded" || raw.includes("free_quota_exceeded")) {
    return "Free tier quota is exhausted. Add your own API key to continue.";
  }
  if (code === "rate_limit" || code === "rate_limit_exceeded") {
    return message ?? "Rate limited. Try again shortly, or continue with your own API key.";
  }
  if (NETWORK_ERROR_RE.test(raw)) {
    return (
      "Could not reach digichat. Start the dev server (make digichat-dev) and " +
      "backend stack (make stack-local), then retry."
    );
  }
  if (raw.includes("embed_disabled") || code === "embed_disabled") {
    return LEGACY_EMBED_DISABLED_MESSAGE;
  }
  if (raw.includes("unauthorized") || code === "unauthorized") {
    return "Sign in on digithings.ai/chat or add your own API key below.";
  }
  if (code != null && BYOK_MODEL_REMEDIABLE_CODES.has(code)) {
    return BYOK_MODEL_REMEDIABLE_MESSAGE;
  }
  if (code && UPSTREAM_ERROR_CODES.has(code)) {
    return (
      message ??
      "digichat could not reach digigraph or digikey. Check make stack-local, then retry."
    );
  }
  return raw.length > 240 ? `${raw.slice(0, 240)}…` : raw;
}
