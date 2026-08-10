"use client";

import { useCallback, useState } from "react";

export type ProviderId = "openrouter" | "openai" | "anthropic" | "gemini";

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
};

export const PROVIDER_LABELS: Record<ProviderId, string> = {
  openrouter: "OpenRouter",
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Gemini",
};

const STORAGE_KEY = "digichat:api_key";
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

function readFromStorage(): ProviderSettings {
  try {
    const apiKey = localStorage.getItem(STORAGE_KEY) ?? "";
    const rawProvider = localStorage.getItem(STORAGE_PROVIDER);
    const provider: ProviderId =
      rawProvider === "openai" ||
      rawProvider === "anthropic" ||
      rawProvider === "gemini" ||
      rawProvider === "openrouter"
        ? rawProvider
        : "openrouter";
    const storedModel = localStorage.getItem(STORAGE_MODEL) ?? "";
    const model =
      storedModel && PROVIDER_MODELS[provider].some((m) => m.id === storedModel)
        ? storedModel
        : defaultModel(provider);
    return { apiKey, provider, model, isSet: apiKey.length > 0 };
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
    try {
      if (trimmed) {
        localStorage.setItem(STORAGE_KEY, trimmed);
        localStorage.setItem(STORAGE_PROVIDER, provider);
        localStorage.setItem(STORAGE_MODEL, resolvedModel);
      } else {
        localStorage.removeItem(STORAGE_KEY);
        localStorage.removeItem(STORAGE_PROVIDER);
        localStorage.removeItem(STORAGE_MODEL);
      }
    } catch {
      /* private mode */
    }
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
