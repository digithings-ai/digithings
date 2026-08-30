import { describe, expect, it } from "vitest";
import {
  BYOK_MODEL_REMEDIABLE_MESSAGE,
  formatEmbedChatError,
  isFreeQuotaOrRateLimitError,
  parseEmbedChatError,
  shouldSuggestByokOnEmbedError,
} from "./embed-chat-error";
import { LEGACY_EMBED_DISABLED_MESSAGE } from "./embed-legacy-gate";

describe("BYOK_MODEL_REMEDIABLE_MESSAGE (#2529)", () => {
  it("points at the in-chat settings affordance, not a full page reload", () => {
    expect(BYOK_MODEL_REMEDIABLE_MESSAGE).toMatch(/Update your key/i);
    expect(BYOK_MODEL_REMEDIABLE_MESSAGE).not.toMatch(/Reload/i);
  });
});

describe("formatEmbedChatError", () => {
  it("returns null for empty errors", () => {
    expect(formatEmbedChatError(undefined)).toBeNull();
  });

  it("parses embed_disabled JSON bodies", () => {
    const msg = formatEmbedChatError(
      new Error(
        JSON.stringify({
          error: "embed_disabled",
          message: LEGACY_EMBED_DISABLED_MESSAGE,
        }),
      ),
    );
    expect(msg).toBe(LEGACY_EMBED_DISABLED_MESSAGE);
  });

  it("detects embed_disabled in plain text", () => {
    expect(formatEmbedChatError(new Error('{"error":"embed_disabled"}'))).toContain(
      "DIGICHAT_EMBED_TENANTS",
    );
  });

  it("parses trial_gate JSON bodies instead of leaking the raw 402 payload", () => {
    const msg = formatEmbedChatError(
      new Error(
        JSON.stringify({
          error: "trial_gate",
          message: "Complete the free trial form to keep chatting.",
        }),
      ),
    );
    expect(msg).toBe("Complete the free trial form to keep chatting.");
  });

  it("surfaces free_quota_exceeded with a BYOK-friendly message", () => {
    const msg = formatEmbedChatError(
      new Error(
        JSON.stringify({
          error: "free_quota_exceeded",
          message: "OpenRouter free quota exhausted.",
        }),
      ),
    );
    expect(msg).toBe("OpenRouter free quota exhausted.");
  });

  it("defaults free_quota_exceeded copy when message is absent", () => {
    expect(
      formatEmbedChatError(new Error(JSON.stringify({ error: "free_quota_exceeded" }))),
    ).toMatch(/Free tier quota/i);
  });

  it("maps fetch failed to a stack hint instead of raw transport text", () => {
    const msg = formatEmbedChatError(new Error("fetch failed"));
    expect(msg).toContain("make digichat-dev");
    expect(msg).toContain("make stack-local");
  });

  it("surfaces upstream_auth message from JSON bodies", () => {
    const msg = formatEmbedChatError(
      new Error(
        JSON.stringify({
          error: "upstream_auth",
          message: "digikey token exchange failed",
        }),
      ),
    );
    expect(msg).toBe("digikey token exchange failed");
  });
});

describe("parseEmbedChatError / isFreeQuotaOrRateLimitError", () => {
  it("parses free_quota_exceeded", () => {
    const p = parseEmbedChatError(
      new Error(JSON.stringify({ error: "free_quota_exceeded", message: "done" })),
    );
    expect(p?.code).toBe("free_quota_exceeded");
    expect(isFreeQuotaOrRateLimitError(p?.code)).toBe(true);
  });

  it("treats rate_limit_exceeded as quota-class", () => {
    expect(isFreeQuotaOrRateLimitError("rate_limit_exceeded")).toBe(true);
    expect(isFreeQuotaOrRateLimitError("rate_limit")).toBe(true);
    expect(isFreeQuotaOrRateLimitError("trial_gate")).toBe(false);
  });
});

describe("shouldSuggestByokOnEmbedError", () => {
  it("suggests BYOK for ungated + free_then_byok on free_quota_exceeded", () => {
    expect(
      shouldSuggestByokOnEmbedError({
        llmAccess: "free_then_byok",
        showByok: true,
        gateMode: "ungated",
        errorCode: "free_quota_exceeded",
      }),
    ).toBe(true);
  });

  it("suggests BYOK for free_then_byok on rate_limit_exceeded", () => {
    expect(
      shouldSuggestByokOnEmbedError({
        llmAccess: "free_then_byok",
        showByok: true,
        gateMode: "ungated",
        errorCode: "rate_limit_exceeded",
      }),
    ).toBe(true);
  });

  it("does not suggest for backend_only (foundry / DataTap-style)", () => {
    expect(
      shouldSuggestByokOnEmbedError({
        llmAccess: "backend_only",
        showByok: false,
        gateMode: "ungated",
        errorCode: "free_quota_exceeded",
      }),
    ).toBe(false);
  });

  it("legacy ungated without llmAccess suppresses BYOK hints", () => {
    expect(
      shouldSuggestByokOnEmbedError({
        showByok: true,
        gateMode: "ungated",
        errorCode: "free_quota_exceeded",
      }),
    ).toBe(false);
  });

  it("legacy turn_limited + showByok suggests on quota", () => {
    expect(
      shouldSuggestByokOnEmbedError({
        showByok: true,
        gateMode: "turn_limited",
        errorCode: "rate_limit_exceeded",
      }),
    ).toBe(true);
  });

  it("never suggests when showByok is false", () => {
    expect(
      shouldSuggestByokOnEmbedError({
        llmAccess: "free_then_byok",
        showByok: false,
        gateMode: "ungated",
        errorCode: "free_quota_exceeded",
      }),
    ).toBe(false);
  });

  it("never suggests BYOK for network or upstream failures", () => {
    expect(
      shouldSuggestByokOnEmbedError({
        llmAccess: "free_then_byok",
        showByok: true,
        gateMode: "ungated",
        errorMessage: "Could not reach digichat.",
      }),
    ).toBe(false);
    expect(
      shouldSuggestByokOnEmbedError({
        llmAccess: "free_then_byok",
        showByok: true,
        gateMode: "turn_limited",
        errorCode: "upstream_auth",
        errorMessage: "digikey token exchange failed",
      }),
    ).toBe(false);
  });
});

describe("model-remediable BYOK refusals (#2490)", () => {
  // digigraph refuses a bound key it cannot spend two ways: `byok_model_required`
  // (a property of the provider) and `byok_default_model_provider_mismatch` (a
  // property of the deployment, which the frontend cannot predict). Both are fixed
  // by naming a model, so both must reopen the BYOK sequence and both must surface
  // digigraph's own message rather than generic quota copy.
  const REMEDIABLE = ["byok_model_required", "byok_default_model_provider_mismatch"] as const;

  for (const errorCode of REMEDIABLE) {
    it(`suggests BYOK for free_then_byok on ${errorCode}`, () => {
      expect(
        shouldSuggestByokOnEmbedError({
          llmAccess: "free_then_byok",
          showByok: true,
          gateMode: "ungated",
          errorCode,
        }),
      ).toBe(true);
    });

    it(`surfaces digigraph's ${errorCode} message verbatim`, () => {
      const message = "Name a model with X-BYOK-Model so your 'openai' key is the one that pays.";
      expect(formatEmbedChatError(new Error(JSON.stringify({ error: errorCode, message })))).toBe(
        message,
      );
    });
  }

  it("does not treat every digigraph refusal as model-remediable", () => {
    // Guards the set, not the branch: `byok_provider_unsupported` is a refusal the
    // user cannot fix by picking a model, so widening the set to "any BYOK code"
    // would wrongly reopen the sequence on a dead end.
    expect(
      shouldSuggestByokOnEmbedError({
        llmAccess: "free_then_byok",
        showByok: true,
        gateMode: "ungated",
        errorCode: "byok_provider_unsupported",
      }),
    ).toBe(false);
  });
});

// The embed transport relays a model-remediable refusal as a bare code — no
// upstream message, because digigraph's reflects the caller's own
// X-BYOK-Provider header. Without copy of our own, a code-only payload fell
// through to the raw-JSON tail and the visitor saw a dead end (#2515).
describe("model-remediable refusals with no upstream message", () => {
  for (const code of ["byok_model_required", "byok_default_model_provider_mismatch"]) {
    it(`gives actionable copy for a bare ${code}`, () => {
      const formatted = formatEmbedChatError(new Error(JSON.stringify({ error: code })));
      expect(formatted).toBe(BYOK_MODEL_REMEDIABLE_MESSAGE);
      expect(formatted).not.toContain("{");
      expect(formatted).not.toContain(code);
    });

    it(`still opens the BYOK sequence for a bare ${code}`, () => {
      const parsed = parseEmbedChatError(new Error(JSON.stringify({ error: code })));
      expect(parsed?.code).toBe(code);
      expect(
        shouldSuggestByokOnEmbedError({
          llmAccess: "free_then_byok",
          gateMode: "ungated",
          errorCode: parsed?.code,
        }),
      ).toBe(true);
    });
  }

  // An upstream message, when there is one, still wins — the SSE path carries it.
  it("prefers the upstream message when one is present", () => {
    const formatted = formatEmbedChatError(
      new Error(JSON.stringify({ error: "byok_model_required", message: "Name a model." })),
    );
    expect(formatted).toBe("Name a model.");
  });
});
