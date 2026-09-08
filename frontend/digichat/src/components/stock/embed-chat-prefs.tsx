"use client";

/**
 * Session-only embed/popup prefs (#3733). Reload and `/new` reset:
 * tools on, language English. Not localStorage.
 */

import { createContext, useContext, type ReactNode } from "react";
import { DEFAULT_LANGUAGE_CODE } from "@/lib/languages";

export type EmbedChatPrefs = {
  webSearch: boolean;
  digisearch: boolean;
  vault: boolean;
  language: string;
};

export const DEFAULT_EMBED_CHAT_PREFS: EmbedChatPrefs = {
  webSearch: true,
  digisearch: true,
  vault: true,
  language: DEFAULT_LANGUAGE_CODE,
};

export type EmbedChatPrefsApi = {
  prefs: EmbedChatPrefs;
  setWebSearch: (value: boolean) => void;
  setDigisearch: (value: boolean) => void;
  setVault: (value: boolean) => void;
  setLanguage: (code: string) => void;
  reset: () => void;
  tenantAllowsWeb: boolean;
  showByok: boolean;
  hasDigisearch: boolean;
  hasVault: boolean;
  sessionKey: string;
  openSettings: () => void;
  openByok: () => void;
  newThread: () => void;
};

const EmbedChatPrefsContext = createContext<EmbedChatPrefsApi | null>(null);

export function EmbedChatPrefsProvider({
  value,
  children,
}: {
  value: EmbedChatPrefsApi;
  children: ReactNode;
}) {
  return (
    <EmbedChatPrefsContext.Provider value={value}>{children}</EmbedChatPrefsContext.Provider>
  );
}

export function useEmbedChatPrefsOptional(): EmbedChatPrefsApi | null {
  return useContext(EmbedChatPrefsContext);
}

export function useEmbedChatPrefs(): EmbedChatPrefsApi {
  const ctx = useContext(EmbedChatPrefsContext);
  if (!ctx) {
    throw new Error("useEmbedChatPrefs requires EmbedChatPrefsProvider");
  }
  return ctx;
}

/** Catalog ids to send as X-Digi-Disabled-Tools (web search uses its own header). */
export function disabledCatalogIds(prefs: EmbedChatPrefs): string[] {
  const out: string[] = [];
  if (!prefs.digisearch) out.push("digisearch");
  if (!prefs.vault) out.push("digivault");
  return out;
}
