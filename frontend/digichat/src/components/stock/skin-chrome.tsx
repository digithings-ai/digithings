"use client";

/**
 * Deploy chrome copy that official assistant-ui templates read at runtime.
 * ProductStockShell provides it. /baseline preview has no provider — skins
 * keep their catalog demo strings.
 */

import { createContext, useContext } from "react";
import {
  DEFAULT_THREAD_SKIN,
  type ThreadSkin,
} from "@/lib/thread-skins";

export type SkinChromeValue = {
  skin: ThreadSkin;
  theme: "dark" | "light";
  title?: string;
  welcome?: string;
  placeholder?: string;
  suggestions: readonly string[];
  accent: { color: string; foreground: string } | null;
  modelPicker: boolean;
};

export const DEFAULT_SKIN_CHROME: SkinChromeValue = {
  skin: DEFAULT_THREAD_SKIN,
  theme: "light",
  suggestions: [],
  accent: null,
  modelPicker: false,
};

const SkinChromeContext = createContext<SkinChromeValue>(DEFAULT_SKIN_CHROME);

export const SkinChromeProvider = SkinChromeContext.Provider;

export function useSkinChrome(): SkinChromeValue {
  return useContext(SkinChromeContext);
}

/** Catalog fallback when deploy YAML omits welcome / placeholder. */
export function useComposerCopy(fallbackWelcome: string, fallbackPlaceholder: string) {
  const chrome = useSkinChrome();
  return {
    title: chrome.title?.trim() || undefined,
    welcome: chrome.welcome?.trim() || fallbackWelcome,
    placeholder: chrome.placeholder?.trim() || fallbackPlaceholder,
    suggestions: chrome.suggestions,
  };
}
