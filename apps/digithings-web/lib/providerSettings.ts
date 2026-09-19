"use client";

import { useCallback, useState } from "react";

export type ProviderId = "openrouter" | "openai" | "anthropic" | "gemini" | "xai";

export type ProviderModel = { id: string; label: string };

export const PROVIDER_MODELS: Record<ProviderId, ProviderModel[]> = {
  openrouter: [
    { id: "openai/gpt-4o-mini", label: "GPT-4o mini" },
    { id: "anthropic/claude-sonnet-4", label: "Claude Sonnet 4" },
    { id: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash" },
    { id: "meta-llama/llama-3.3-70b-instruct", label: "Llama 3.3 70B" },
    { id: "deepseek/deepseek-chat-v3", label: "DeepSeek V3" },
  ],
  openai: [
    { id: "gpt-4o-mini", label: "GPT-4o mini" },
    { id: "gpt-4o", label: "GPT-4o" },
    { id: "gpt-4.1-mini", label: "GPT-4.1 mini" },
  ],
  anthropic: [
    { id: "claude-sonnet-4-20250514", label: "Claude Sonnet 4" },
    { id: "claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku" },
  ],
  gemini: [
    { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
    { id: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
  ],
  xai: [
    { id: "grok-4-3", label: "Grok 4.3" },
    { id: "grok-4.5", label: "Grok 4.5" },
  ],
};

export const PROVIDER_LABELS: Record<ProviderId, string> = {
  openrouter: "OpenRouter",
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Gemini",
  xai: "xAI",
};

// Legacy durable key — no longer written. Purged on load if a prior build
// left one behind; never read back into state. See #2348.
const LEGACY_STORAGE_KEY = "digichat:api_key";
const STORAGE_PROVIDER = "digichat:provider";
const STORAGE_MODEL = "digichat:model";

export type ProviderSettings = {
  apiKey: string;
  provider: ProviderId;
  model: string;
  isSet: boolean;
};

function defaultModel(provider: ProviderId): string {
  return PROVIDER_MODELS[provider][0]?.id ?? "";
}

/**
 * Remove any leftover durable BYOK key from prior builds. The key must never
 * live in localStorage — it now lives only in React state for the tab
 * session (see `useProviderSettings`), matching digichat's
 * `purgeDurableByokKeys()` pattern (including the `typeof window` guard and
 * clearing sessionStorage too, in case a future build ever writes there).
 *
 * Called unconditionally on every digithings-web page load from
 * `components/LegacyByokPurge.tsx` (mounted from the root layout) — not just
 * from `useProviderSettings`, whose historical consumer was an in-process
 * session widget that `/chat` and `/chat/occ` no longer mount (they use
 * `ChatEmbedShell` → digichat `/embed`). See #2348.
 *
 * Exported (alongside the two helpers below) purely so tests can exercise
 * this module's storage behavior directly — `useProviderSettings` calls
 * hooks internally and so can't be invoked outside a React render.
 */
export function purgeLegacyApiKey(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    window.sessionStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    /* private mode / SSR */
  }
}

/**
 * Persist only the non-secret provider/model preference. Never writes the
 * BYOK key itself — that lives in React state for the tab session only.
 */
export function persistProviderPreference(
  trimmedKey: string,
  provider: ProviderId,
  model: string,
): void {
  try {
    purgeLegacyApiKey();
    if (trimmedKey) {
      localStorage.setItem(STORAGE_PROVIDER, provider);
      localStorage.setItem(STORAGE_MODEL, model);
    } else {
      localStorage.removeItem(STORAGE_PROVIDER);
      localStorage.removeItem(STORAGE_MODEL);
    }
  } catch {
    /* private mode */
  }
}

export function readFromStorage(): ProviderSettings {
  purgeLegacyApiKey();
  try {
    const rawProvider = localStorage.getItem(STORAGE_PROVIDER);
    const provider: ProviderId =
      rawProvider === "openai" ||
      rawProvider === "anthropic" ||
      rawProvider === "gemini" ||
      rawProvider === "xai" ||
      rawProvider === "openrouter"
        ? rawProvider
        : "openrouter";
    const storedModel = localStorage.getItem(STORAGE_MODEL) ?? "";
    const model =
      storedModel && PROVIDER_MODELS[provider].some((m) => m.id === storedModel)
        ? storedModel
        : defaultModel(provider);
    // The key itself is never persisted — every load starts session-only.
    return { apiKey: "", provider, model, isSet: false };
  } catch {
    return { apiKey: "", provider: "openrouter", model: defaultModel("openrouter"), isSet: false };
  }
}

export function validateProviderKey(key: string, provider: ProviderId): string | null {
  const trimmed = key.trim();
  if (!trimmed) return "API key is required.";
  switch (provider) {
    case "openrouter":
      if (!trimmed.startsWith("sk-or-")) return "OpenRouter keys start with sk-or-.";
      break;
    case "openai":
      if (!trimmed.startsWith("sk-")) return "OpenAI keys start with sk-.";
      break;
    case "anthropic":
      if (!trimmed.startsWith("sk-ant-")) return "Anthropic keys start with sk-ant-.";
      break;
    case "gemini":
      if (!trimmed.startsWith("AI")) return "Gemini keys start with AI.";
      break;
    case "xai":
      if (!trimmed.startsWith("xai-")) return "x.ai keys start with xai-.";
      break;
    default: {
      const _exhaustive: never = provider;
      return _exhaustive;
    }
  }
  return null;
}

export function useProviderSettings() {
  const [state, setState] = useState<ProviderSettings>(readFromStorage);

  const save = useCallback((apiKey: string, provider: ProviderId, model: string) => {
    const trimmed = apiKey.trim();
    const resolvedModel =
      model && PROVIDER_MODELS[provider].some((m) => m.id === model)
        ? model
        : defaultModel(provider);
    persistProviderPreference(trimmed, provider, resolvedModel);
    setState({
      apiKey: trimmed,
      provider,
      model: resolvedModel,
      isSet: trimmed.length > 0,
    });
  }, []);

  const clear = useCallback(() => save("", "openrouter", defaultModel("openrouter")), [save]);

  return { ...state, save, clear };
}

export function providerSummary(settings: ProviderSettings): string {
  if (!settings.isSet) return "free pool";
  const label = PROVIDER_LABELS[settings.provider];
  const model =
    PROVIDER_MODELS[settings.provider].find((m) => m.id === settings.model)?.label ??
    settings.model;
  return `${label} · ${model}`;
}
