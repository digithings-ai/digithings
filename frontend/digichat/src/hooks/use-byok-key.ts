"use client";

import { useCallback, useState } from "react";
import { isOpenRouterKey } from "@/lib/byok-openrouter";

export type BYOKProvider = "openai" | "anthropic" | "openrouter" | "gemini" | "xai";

export const BYOK_PROVIDER_LIST: readonly BYOKProvider[] = [
  "openrouter",
  "openai",
  "anthropic",
  "gemini",
  "xai",
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
    case "xai":
      return "grok-4-3";
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
    case "xai":
      return ["grok-4-3", "grok-4.5"];
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

const BYOK_PREF_COOKIE = "digichat_byok_pref";
const BYOK_PREF_COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year — non-secret preference only

/** Non-secret provider+model choice, persisted so a returning visitor's picker opens
 * pre-selected. The key itself is NEVER written here — see useBYOKKey's own doc
 * comment. Plain client-side cookie (not httpOnly): read/write directly from the
 * browser, no server round-trip.
 *
 * Known limitation on /embed: that surface is a cross-site iframe, where
 * `document.cookie` access is blocked or partitioned by default in Safari and
 * Firefox, and needs `Partitioned` (CHIPS) in Chrome to survive third-party-
 * cookie blocking. This preference silently won't persist there in a
 * cookie-blocking browser — nothing breaks, the picker just falls back to its
 * default. CHIPS is out of scope here; the authenticated app shell (not a
 * cross-site iframe) is unaffected. */
export function readByokPrefCookie(): { provider: BYOKProvider; model: string } | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${BYOK_PREF_COOKIE}=`));
  if (!match) return null;
  try {
    const raw = decodeURIComponent(match.slice(BYOK_PREF_COOKIE.length + 1));
    const parsed = JSON.parse(raw) as { p?: string; m?: string };
    if (!parsed.p || !(BYOK_PROVIDER_LIST as readonly string[]).includes(parsed.p)) return null;
    return { provider: parsed.p as BYOKProvider, model: parsed.m ?? "" };
  } catch {
    return null;
  }
}

export function writeByokPrefCookie(provider: BYOKProvider, model: string): void {
  if (typeof document === "undefined") return;
  const value = encodeURIComponent(JSON.stringify({ p: provider, m: model }));
  // `; Secure` only when actually on https — an unconditional Secure would silently
  // stop the browser from storing the cookie at all on local http dev (and in any
  // test environment whose document URL isn't https), breaking the whole feature
  // there rather than just tightening it in production.
  const secure =
    typeof location !== "undefined" && location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${BYOK_PREF_COOKIE}=${value}; path=/; max-age=${BYOK_PREF_COOKIE_MAX_AGE}; SameSite=Lax${secure}`;
}

/** Delete the preference cookie outright (not a rewrite to a default value) —
 * used by clearKey() below. Must match writeByokPrefCookie's `path=/` exactly:
 * a cookie is keyed by (name, path), so a delete without a matching path
 * leaves the original untouched instead of removing it. */
export function deleteByokPrefCookie(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${BYOK_PREF_COOKIE}=; path=/; max-age=0`;
}

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
 * The key itself is never written to localStorage, sessionStorage, cookies,
 * or the server. A separate non-secret cookie (`digichat_byok_pref`, see
 * readByokPrefCookie/writeByokPrefCookie above) persists only the provider
 * and model identifiers so a returning visitor's picker opens pre-selected —
 * the key argument to setKey is never passed into that cookie write.
 */
export function useBYOKKey() {
  const [state, setState] = useState<BYOKKeyState>(() => {
    purgeDurableByokKeys();
    const pref = readByokPrefCookie();
    return pref
      ? { key: "", provider: pref.provider, model: pref.model, isSet: false }
      : emptyByokState();
  });

  const setKey = useCallback((key: string, provider: BYOKProvider, model = "") => {
    // Defense in depth: never leave durable leftovers if an older build wrote them.
    purgeDurableByokKeys();
    // Non-secret preference only — `key` is intentionally never passed here.
    writeByokPrefCookie(provider, model);
    setState({ key, provider, model, isSet: key.length > 0 });
  }, []);

  const clearKey = useCallback(() => {
    // Not setKey("", "openrouter", "") — that routes through writeByokPrefCookie
    // and would silently reset the remembered provider/model preference to
    // openrouter instead of removing it. "Clear my key" must not touch the
    // preference cookie at all beyond deleting it outright.
    purgeDurableByokKeys();
    deleteByokPrefCookie();
    setState(emptyByokState());
  }, []);

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
  if (provider === "xai" && !key.startsWith("xai-")) {
    return "x.ai keys must start with xai-.";
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
