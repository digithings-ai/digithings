"use client";

/**
 * Deploy chrome copy that official assistant-ui templates read at runtime.
 * ProductStockShell provides it. /baseline preview has no provider — skins
 * keep their catalog demo strings.
 */

import { createContext, useContext } from "react";
import { DEFAULT_THREAD_SKIN, type ThreadSkin } from "../skins/thread-skins";
import type { ChromeMode, PageContextMode } from "./skin-types";

export type SkinChromeValue = {
  skin: ThreadSkin;
  theme: "dark" | "light";
  /** Deploy `chrome.mode`. Compact composer on embed / modal / sidebar. */
  mode: ChromeMode;
  title?: string;
  welcome?: string;
  welcomeBody?: readonly string[];
  placeholder?: string;
  suggestions: readonly string[];
  accent: { color: string; foreground: string } | null;
  modelPicker: boolean;
  /**
   * Deploy `features.pageContext`. `silent` keeps the system
   * `page-context.html` attachment out of the composer and sent-message chips.
   */
  pageContext: PageContextMode;
  /**
   * Whether the "powered by digichat" credit may render on this surface.
   *
   * Resolved by the host from the deployment / embed tenant
   * (`chrome.attribution` / `tenantCfg.attribution`), so an explicit
   * `attribution: false` opt-out suppresses the skin's credit. Without this the
   * embed's opt-out was ignored (the skins mounted the credit unconditionally),
   * and a titled opted-out tenant rendered two credits — the header
   * parenthetical *and* the skin footer (m2502 review, M2).
   */
  attribution: boolean;
};

export const DEFAULT_SKIN_CHROME: SkinChromeValue = {
  skin: DEFAULT_THREAD_SKIN,
  theme: "light",
  mode: "embed",
  suggestions: [],
  accent: null,
  modelPicker: false,
  pageContext: "visible",
  attribution: true,
};

const SkinChromeContext = createContext<SkinChromeValue>(DEFAULT_SKIN_CHROME);

export const SkinChromeProvider = SkinChromeContext.Provider;

export function useSkinChrome(): SkinChromeValue {
  return useContext(SkinChromeContext);
}

/**
 * Whether the surface may render the credit. Defaults to `true` off the
 * provider (`/baseline` preview, catalog demos) so the credit appears by
 * default; a host that resolved `attribution: false` from config turns it off.
 */
export function useAttribution(): boolean {
  return useContext(SkinChromeContext).attribution;
}

/** Catalog fallback when deploy YAML omits welcome / placeholder. */
export function useComposerCopy(fallbackWelcome: string, fallbackPlaceholder: string) {
  const chrome = useSkinChrome();
  return {
    title: chrome.title?.trim() || undefined,
    welcome: chrome.welcome?.trim() || fallbackWelcome,
    welcomeBody: chrome.welcomeBody ?? [],
    placeholder: chrome.placeholder?.trim() || fallbackPlaceholder,
    suggestions: chrome.suggestions,
  };
}
