import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  isOpenRouterKey,
  normalizeOpenRouterModel,
} from "@/lib/byok-openrouter";
import {
  BYOK_DURABLE_STORAGE_KEYS,
  byokModelPlaceholder,
  byokModelPresets,
  emptyByokState,
  moveListIndex,
  purgeDurableByokKeys,
  validateBYOKKey,
  validateBYOKModel,
} from "@/hooks/use-byok-key";
import { byokActivationGate } from "@/lib/byok-ping";

describe("validateBYOKKey", () => {
  it("returns null for a valid OpenAI key", () => {
    expect(validateBYOKKey("sk-proj-abc123", "openai")).toBeNull();
  });

  it("returns null for a valid Anthropic key", () => {
    expect(validateBYOKKey("sk-ant-api03-xyz", "anthropic")).toBeNull();
  });

  it("returns null for a valid OpenRouter key", () => {
    expect(validateBYOKKey("sk-or-v1-abc123", "openrouter")).toBeNull();
  });

  it("errors on empty key", () => {
    expect(validateBYOKKey("", "openai")).not.toBeNull();
  });

  it("errors when OpenAI key does not start with sk-", () => {
    expect(validateBYOKKey("not-a-key", "openai")).toMatch(/sk-/);
  });

  it("errors when Anthropic key does not start with sk-ant-", () => {
    expect(validateBYOKKey("sk-wrong", "anthropic")).toMatch(/sk-ant-/);
  });

  it("errors when OpenRouter key does not start with sk-or-", () => {
    expect(validateBYOKKey("sk-proj-abc", "openrouter")).toMatch(/sk-or-/);
  });

  it("accepts OpenAI key starting with sk- that contains ant (not a prefix match confusion)", () => {
    expect(validateBYOKKey("sk-ant-bad", "openai")).toBeNull();
  });

  it("rejects Anthropic key that only starts with sk-", () => {
    expect(validateBYOKKey("sk-only", "anthropic")).not.toBeNull();
  });

  it("returns null for a valid x.ai key", () => {
    expect(validateBYOKKey("xai-test123", "xai")).toBeNull();
  });

  it("errors when x.ai key does not start with xai-", () => {
    expect(validateBYOKKey("not-xai", "xai")).toMatch(/xai-/);
  });
});

describe("validateBYOKModel", () => {
  it("requires model for OpenRouter", () => {
    expect(validateBYOKModel("", "openrouter")).not.toBeNull();
    expect(validateBYOKModel("openai/gpt-4o-mini", "openrouter")).toBeNull();
  });

  it("requires model for Anthropic and Gemini", () => {
    expect(validateBYOKModel("", "anthropic")).not.toBeNull();
    expect(validateBYOKModel("claude-sonnet-4-20250514", "anthropic")).toBeNull();
    expect(validateBYOKModel("", "gemini")).not.toBeNull();
    expect(validateBYOKModel("gemini/gemini-2.0-flash", "gemini")).toBeNull();
  });

  it("requires model for x.ai", () => {
    expect(validateBYOKModel("", "xai")).not.toBeNull();
    expect(validateBYOKModel("grok-4-3", "xai")).toBeNull();
  });

  it("does not require model for OpenAI", () => {
    expect(validateBYOKModel("", "openai")).toBeNull();
  });
});

describe("byokModelPlaceholder", () => {
  it("returns non-empty placeholder for x.ai", () => {
    expect(byokModelPlaceholder("xai")).toBeTruthy();
  });
});

describe("normalizeOpenRouterModel", () => {
  it("strips openrouter/ prefix", () => {
    expect(normalizeOpenRouterModel("openrouter/openai/gpt-4o")).toBe("openai/gpt-4o");
  });

  it("passes through bare slugs", () => {
    expect(normalizeOpenRouterModel("anthropic/claude-sonnet-4")).toBe(
      "anthropic/claude-sonnet-4"
    );
  });
});

describe("isOpenRouterKey", () => {
  it("matches sk-or- prefix", () => {
    expect(isOpenRouterKey("sk-or-v1-test")).toBe(true);
    expect(isOpenRouterKey("sk-proj-test")).toBe(false);
  });
});

describe("session-only BYOK storage", () => {
  const memory = new Map<string, string>();

  beforeEach(() => {
    memory.clear();
    const store = {
      getItem: (k: string) => memory.get(k) ?? null,
      setItem: (k: string, v: string) => {
        memory.set(k, v);
      },
      removeItem: (k: string) => {
        memory.delete(k);
      },
      clear: () => memory.clear(),
      key: () => null,
      get length() {
        return memory.size;
      },
    };
    vi.stubGlobal("localStorage", store);
    vi.stubGlobal("sessionStorage", store);
    // window needed for purgeDurableByokKeys
    vi.stubGlobal("window", { localStorage: store, sessionStorage: store });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("purges legacy durable BYOK keys from localStorage and sessionStorage", () => {
    for (const k of BYOK_DURABLE_STORAGE_KEYS) {
      memory.set(k, "secret");
    }
    purgeDurableByokKeys();
    for (const k of BYOK_DURABLE_STORAGE_KEYS) {
      expect(memory.has(k)).toBe(false);
    }
  });

  it("emptyByokState starts unset with no key material", () => {
    const s = emptyByokState();
    expect(s.isSet).toBe(false);
    expect(s.key).toBe("");
  });

  it("documents that durable key names must never be written (regression sentinel)", () => {
    // If a future change re-introduces localStorage writes, this list is the
    // contract tests + purge both rely on — keep it exhaustive.
    expect([...BYOK_DURABLE_STORAGE_KEYS]).toEqual([
      "byok_api_key",
      "byok_provider",
      "byok_model",
    ]);
  });
});

describe("moveListIndex (keyboard selection)", () => {
  it("moves down and wraps", () => {
    expect(moveListIndex(0, 4, "down")).toBe(1);
    expect(moveListIndex(3, 4, "down")).toBe(0);
  });

  it("moves up and wraps", () => {
    expect(moveListIndex(0, 4, "up")).toBe(3);
    expect(moveListIndex(2, 4, "up")).toBe(1);
  });

  it("handles empty lists safely", () => {
    expect(moveListIndex(0, 0, "down")).toBe(0);
  });
});

describe("byokActivationGate (validation before session activate)", () => {
  it("refuses when ping has not run", () => {
    expect(byokActivationGate(null)).toMatch(/Validate/);
  });

  it("refuses failed pings", () => {
    expect(byokActivationGate({ ok: false, error: "bad key" })).toBe("bad key");
  });

  it("allows only successful pings", () => {
    expect(byokActivationGate({ ok: true, model: "gpt-4o-mini" })).toBeNull();
  });
});

describe("byokModelPresets", () => {
  it("returns non-empty presets for every provider", () => {
    for (const p of ["openrouter", "openai", "anthropic", "gemini", "xai"] as const) {
      expect(byokModelPresets(p).length).toBeGreaterThan(0);
    }
  });
});
