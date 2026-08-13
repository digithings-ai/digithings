"use client";

import { useCallback, useState } from "react";
import { isOpenRouterKey } from "@/lib/byok-openrouter";

export type BYOKProvider = "openai" | "anthropic" | "openrouter" | "gemini";

export const BYOK_PROVIDER_LIST: readonly BYOKProvider[] = [
  "openrouter",
  "openai",
  "anthropic",
  "gemini",
];

/** Legacy durable keys — purged on load; never written again. */
export const BYOK_DURABLE_STORAGE_KEYS = [
  "byok_api_key",
  "byok_provider",
  "byok_model",
] as const;

/** Non-OpenAI BYOK requires an explicit model slug (digigraph spend path). */
export function byokRequiresModel(provider: BYOKProvider): boolean {
  return provider !== "openai";
}

export function byokModelPlaceholder(provider: BYOKProvider): string {
  switch (provider) {
    case "openrouter":
      return "openai/gpt-4o-mini";
    case "anthropic":
      return "claude-sonnet-4-20250514";
    case "gemini":
      return "gemini/gemini-2.0-flash";
    case "openai":
      return "gpt-4o-mini";
    default: {
      const _exhaustive: never = provider;
      return _exhaustive;
    }
  }
}

/** Preset model slugs shown in the terminal model picker. */
export function byokModelPresets(provider: BYOKProvider): readonly string[] {
  switch (provider) {
    case "openrouter":
      return [
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "anthropic/claude-sonnet-4",
        "google/gemini-2.0-flash",
      ];
    case "openai":
      return ["gpt-4o-mini", "gpt-4o", "o4-mini"];
    case "anthropic":
      return [
        "claude-sonnet-4-20250514",
        "claude-haiku-4-20250514",
        "claude-opus-4-20250514",
      ];
    case "gemini":
      return [
        "gemini/gemini-2.0-flash",
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-pro",
      ];
    default: {
      const _exhaustive: never = provider;
      return _exhaustive;
    }
  }
}

export type BYOKKeyState = {
  key: string;
  provider: BYOKProvider;
  model: string;
  isSet: boolean;
};

/** A single model entry once live catalog data exists (Task 8+). Falls back to a
 * flat string per fallbackModels entry with tier undefined when live fetch hasn't
 * run or failed — the picker never blocks on the network. */
export type ByokModelOption = {
  id: string;
  label: string;
  tier?: "free" | "opensource" | "flagship";
  supportsTools?: boolean;
};

export function emptyByokState(
  provider: BYOKProvider = "openrouter",
): BYOKKeyState {
  return { key: "", provider, model: "", isSet: false };
}

/**
 * Remove any leftover durable BYOK material from prior builds.
 * Keys must never live in localStorage / sessionStorage.
 */
export function purgeDurableByokKeys(): void {
  if (typeof window === "undefined") return;
  try {
    for (const k of BYOK_DURABLE_STORAGE_KEYS) {
      window.localStorage.removeItem(k);
      window.sessionStorage.removeItem(k);
    }
  } catch {
    // private mode / SSR
  }
}

/** Arrow-key highlight movement for terminal option lists (wraps). */
export function moveListIndex(
  index: number,
  length: number,
  direction: "up" | "down",
): number {
  if (length <= 0) return 0;
  if (direction === "down") return (index + 1) % length;
  return (index - 1 + length) % length;
}

/**
 * Session-only BYOK key holder.
 *
 * Keys live in React state for this tab session. Refresh / new tab → gone.
 * Never writes localStorage, sessionStorage, cookies, or the server.
 */
export function useBYOKKey() {
  const [state, setState] = useState<BYOKKeyState>(() => {
    purgeDurableByokKeys();
    return emptyByokState();
  });

  const setKey = useCallback((key: string, provider: BYOKProvider, model = "") => {
    // Defense in depth: never leave durable leftovers if an older build wrote them.
    purgeDurableByokKeys();
    setState({ key, provider, model, isSet: key.length > 0 });
  }, []);

  const clearKey = useCallback(() => setKey("", "openrouter", ""), [setKey]);

  return { ...state, setKey, clearKey };
}

/** Validate key format. Returns null if valid, or an error message. */
export function validateBYOKKey(key: string, provider: BYOKProvider): string | null {
  if (!key.trim()) return "API key is required.";
  if (provider === "openai" && !key.startsWith("sk-")) {
    return "OpenAI keys must start with sk-.";
  }
  if (provider === "anthropic" && !key.startsWith("sk-ant-")) {
    return "Anthropic keys must start with sk-ant-.";
  }
  if (provider === "openrouter" && !isOpenRouterKey(key)) {
    return "OpenRouter keys must start with sk-or-.";
  }
  if (provider === "gemini" && !key.startsWith("AI")) {
    return "Gemini keys must start with AI.";
  }
  return null;
}

/** Validate model when required (all non-OpenAI providers). Returns null if valid. */
export function validateBYOKModel(model: string, provider: BYOKProvider): string | null {
  if (!byokRequiresModel(provider)) return null;
  if (!model.trim()) {
    const hint = byokModelPlaceholder(provider);
    return `Model is required for ${provider}${hint ? ` (e.g. ${hint})` : ""}.`;
  }
  return null;
}
