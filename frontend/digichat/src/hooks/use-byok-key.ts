"use client";

import { useCallback, useState } from "react";
import { isOpenRouterKey } from "@/lib/byok-openrouter";

export type BYOKProvider = "openai" | "anthropic" | "openrouter";

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
  return null;
}

/** Validate model when required (OpenRouter). Returns null if valid. */
export function validateBYOKModel(model: string, provider: BYOKProvider): string | null {
  if (provider !== "openrouter") return null;
  if (!model.trim()) {
    return "Model is required for OpenRouter (e.g. openai/gpt-4o-mini).";
  }
  return null;
}
