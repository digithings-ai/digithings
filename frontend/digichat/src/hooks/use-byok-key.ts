"use client";

import { useCallback, useState } from "react";

export type BYOKProvider = "openai" | "anthropic";

export type BYOKKeyState = {
  key: string;
  provider: BYOKProvider;
  isSet: boolean;
};

const STORAGE_KEY = "byok_api_key";
const STORAGE_PROVIDER_KEY = "byok_provider";

function readFromStorage(): BYOKKeyState {
  try {
    const key = localStorage.getItem(STORAGE_KEY) ?? "";
    const rawProvider = localStorage.getItem(STORAGE_PROVIDER_KEY);
    const provider: BYOKProvider =
      rawProvider === "anthropic" ? "anthropic" : "openai";
    return { key, provider, isSet: key.length > 0 };
  } catch {
    // localStorage not available in SSR or private mode
    return { key: "", provider: "openai", isSet: false };
  }
}

export function useBYOKKey() {
  // Lazy initializer runs once on mount (client-only); avoids SSR mismatch
  const [state, setState] = useState<BYOKKeyState>(readFromStorage);

  const setKey = useCallback((key: string, provider: BYOKProvider) => {
    try {
      if (key) {
        localStorage.setItem(STORAGE_KEY, key);
        localStorage.setItem(STORAGE_PROVIDER_KEY, provider);
      } else {
        localStorage.removeItem(STORAGE_KEY);
        localStorage.removeItem(STORAGE_PROVIDER_KEY);
      }
    } catch {
      // localStorage not available (SSR guard, private mode)
    }
    setState({ key, provider, isSet: key.length > 0 });
  }, []);

  const clearKey = useCallback(() => setKey("", "openai"), [setKey]);

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
  return null;
}
