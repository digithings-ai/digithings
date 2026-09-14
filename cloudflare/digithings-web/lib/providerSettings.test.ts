import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  PROVIDER_LABELS,
  PROVIDER_MODELS,
  persistProviderPreference,
  purgeLegacyApiKey,
  readFromStorage,
  validateProviderKey,
} from "./providerSettings";

describe("providerSettings", () => {
  let store: Map<string, string>;
  let setItemSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    store = new Map<string, string>();
    setItemSpy = vi.fn((k: string, v: string) => {
      store.set(k, v);
    });
    // One shared store standing in for both localStorage and sessionStorage,
    // plus a `window` stub carrying both -- mirrors digichat's
    // `use-byok-key.test.ts` setup, needed now that `purgeLegacyApiKey` reads
    // `window.localStorage` / `window.sessionStorage` (#2348 finding 6).
    const storageLike = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: setItemSpy,
      removeItem: (k: string) => {
        store.delete(k);
      },
    };
    vi.stubGlobal("localStorage", storageLike);
    vi.stubGlobal("sessionStorage", storageLike);
    vi.stubGlobal("window", { localStorage: storageLike, sessionStorage: storageLike });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("xai provider (added by #2348)", () => {
    it("is a recognized provider with model presets and a label", () => {
      expect(PROVIDER_MODELS.xai.map((m) => m.id)).toEqual(["grok-4-3", "grok-4.5"]);
      expect(PROVIDER_LABELS.xai).toBe("xAI");
    });

    it("rejects keys that don't start with xai-", () => {
      expect(validateProviderKey("sk-not-xai", "xai")).toBe("x.ai keys start with xai-.");
    });

    it("accepts a properly-prefixed key", () => {
      expect(validateProviderKey("xai-realkey", "xai")).toBeNull();
    });

    it("is read back correctly as a stored provider preference", () => {
      store.set("digichat:provider", "xai");
      store.set("digichat:model", "grok-4.5");
      const settings = readFromStorage();
      expect(settings.provider).toBe("xai");
      expect(settings.model).toBe("grok-4.5");
    });
  });

  describe("the BYOK key is never persisted to localStorage (#2348)", () => {
    it("never calls localStorage.setItem with the raw key, or under the legacy key name", () => {
      persistProviderPreference("xai-super-secret-key", "xai", "grok-4-3");

      for (const call of setItemSpy.mock.calls) {
        const [storedKeyName, storedValue] = call as [string, string];
        expect(storedKeyName).not.toBe("digichat:api_key");
        expect(storedValue).not.toContain("xai-super-secret-key");
      }
      expect(store.has("digichat:api_key")).toBe(false);
    });

    it("still persists the non-secret provider/model preference", () => {
      persistProviderPreference("xai-super-secret-key", "xai", "grok-4-3");
      expect(store.get("digichat:provider")).toBe("xai");
      expect(store.get("digichat:model")).toBe("grok-4-3");
    });

    it("clears provider/model preference when the key is cleared (empty trimmed key)", () => {
      store.set("digichat:provider", "xai");
      store.set("digichat:model", "grok-4-3");
      persistProviderPreference("", "openrouter", "openai/gpt-4o-mini");
      expect(store.has("digichat:provider")).toBe(false);
      expect(store.has("digichat:model")).toBe(false);
    });
  });

  describe("legacy digichat:api_key is purged, not read back (#2348)", () => {
    it("purgeLegacyApiKey removes a pre-existing leaked key", () => {
      store.set("digichat:api_key", "sk-leaked");
      purgeLegacyApiKey();
      expect(store.has("digichat:api_key")).toBe(false);
    });

    it("readFromStorage purges a legacy key and never re-populates apiKey/isSet from it", () => {
      store.set("digichat:api_key", "sk-leaked");
      store.set("digichat:provider", "openai");
      store.set("digichat:model", "gpt-4o");

      const settings = readFromStorage();

      expect(store.has("digichat:api_key")).toBe(false);
      expect(settings.apiKey).toBe("");
      expect(settings.isSet).toBe(false);
      // Non-secret prefs are unaffected by the purge.
      expect(settings.provider).toBe("openai");
      expect(settings.model).toBe("gpt-4o");
    });

    it("readFromStorage always starts session-only even with no legacy key present", () => {
      const settings = readFromStorage();
      expect(settings.apiKey).toBe("");
      expect(settings.isSet).toBe(false);
    });
  });

  describe("purge also clears sessionStorage and guards SSR (#2348 minor finding 6)", () => {
    it("removes the legacy key from sessionStorage too, not just localStorage", () => {
      store.set("digichat:api_key", "sk-leaked");
      purgeLegacyApiKey();
      expect(store.has("digichat:api_key")).toBe(false);
      // Confirms the sessionStorage-qualified removeItem path actually ran,
      // not just the localStorage one.
      expect(sessionStorage.getItem("digichat:api_key")).toBeNull();
    });

    it("no-ops without throwing when window is undefined (SSR)", () => {
      vi.stubGlobal("window", undefined);
      expect(() => purgeLegacyApiKey()).not.toThrow();
    });
  });

  describe("existing providers are unaffected", () => {
    it("still validates openrouter/openai/anthropic/gemini prefixes as before", () => {
      expect(validateProviderKey("bad", "openrouter")).toBe("OpenRouter keys start with sk-or-.");
      expect(validateProviderKey("sk-or-real", "openrouter")).toBeNull();
      expect(validateProviderKey("bad", "openai")).toBe("OpenAI keys start with sk-.");
      expect(validateProviderKey("sk-real", "openai")).toBeNull();
      expect(validateProviderKey("bad", "anthropic")).toBe("Anthropic keys start with sk-ant-.");
      expect(validateProviderKey("sk-ant-real", "anthropic")).toBeNull();
      expect(validateProviderKey("bad", "gemini")).toBe("Gemini keys start with AI.");
      expect(validateProviderKey("AIreal", "gemini")).toBeNull();
    });

    it("falls back to openrouter for a corrupted/unrecognized stored provider value", () => {
      store.set("digichat:provider", "not-a-real-provider");
      const settings = readFromStorage();
      expect(settings.provider).toBe("openrouter");
    });
  });
});
