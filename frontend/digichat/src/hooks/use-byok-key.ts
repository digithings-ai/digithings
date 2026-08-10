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
      return "";
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

const STORAGE_KEY = "byok_api_key";
const STORAGE_PROVIDER_KEY = "byok_provider";
const STORAGE_MODEL_KEY = "byok_model";

function readProvider(raw: string | null): BYOKProvider {
  if (raw === "anthropic") return "anthropic";
  if (raw === "openrouter") return "openrouter";
  if (raw === "gemini") return "gemini";
  return "openai";
}

function readFromStorage(): BYOKKeyState {
  try {
    const key = localStorage.getItem(STORAGE_KEY) ?? "";
    const provider = readProvider(localStorage.getItem(STORAGE_PROVIDER_KEY));
    const model = localStorage.getItem(STORAGE_MODEL_KEY) ?? "";
    return { key, provider, model, isSet: key.length > 0 };
  } catch {
    return { key: "", provider: "openai", model: "", isSet: false };
  }
}

export function useBYOKKey() {
  const [state, setState] = useState<BYOKKeyState>(readFromStorage);

  const setKey = useCallback((key: string, provider: BYOKProvider, model = "") => {
    try {
      if (key) {
        localStorage.setItem(STORAGE_KEY, key);
        localStorage.setItem(STORAGE_PROVIDER_KEY, provider);
        localStorage.setItem(STORAGE_MODEL_KEY, model);
      } else {
        localStorage.removeItem(STORAGE_KEY);
        localStorage.removeItem(STORAGE_PROVIDER_KEY);
        localStorage.removeItem(STORAGE_MODEL_KEY);
      }
    } catch {
      // localStorage not available (SSR guard, private mode)
    }
    setState({ key, provider, model, isSet: key.length > 0 });
  }, []);

  const clearKey = useCallback(() => setKey("", "openai", ""), [setKey]);

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
