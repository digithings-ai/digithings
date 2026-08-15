/** Client-side embed UI overrides from iframe URL search params. */

import { isEmbedHexColor } from "@/lib/embed-accent-style";

export type EmbedUiParams = {
  welcome?: string;
  placeholder?: string;
  suggestions?: string[];
  /** Accent color override (#rrggbb) — the embedding site theming the widget
   * to its own brand, same override channel as welcome/placeholder. */
  accent?: string;
  accentForeground?: string;
  /** `?wide=1` — drop the `.dc-session` 1080px cap. Opt-in per embedder (full-page
   * hosts like digithings.ai /chat and /chat/occ), not a tenant-config default,
   * so narrow widget embeds elsewhere keep the readable-column width. */
  wide?: boolean;
};

function readHexParam(sp: URLSearchParams, key: string): string | undefined {
  const raw = sp.get(key);
  return isEmbedHexColor(raw) ? raw : undefined;
}

export function readEmbedUiParams(search: string): EmbedUiParams {
  const sp = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const welcome = sp.get("welcome") ?? undefined;
  const placeholder = sp.get("placeholder") ?? undefined;
  const accent = readHexParam(sp, "accent");
  const accentForeground = readHexParam(sp, "accentForeground");
  const rawSuggestions = sp.get("suggestions");
  let suggestions: string[] | undefined;
  if (rawSuggestions) {
    try {
      const parsed = JSON.parse(rawSuggestions) as unknown;
      if (Array.isArray(parsed)) {
        suggestions = parsed.filter((s): s is string => typeof s === "string" && s.trim().length > 0);
      }
    } catch {
      suggestions = rawSuggestions
        .split("|")
        .map((s) => s.trim())
        .filter(Boolean);
    }
  }
  // undefined, not false, when absent — matches every other optional field
  // here (accent, welcome, ...): existing callers' `toEqual({...})` checks
  // compare against an object that omits the key entirely, and `toEqual`
  // treats `undefined`-valued keys as absent but not `false`-valued ones.
  const wide = sp.get("wide") === "1" ? true : undefined;
  return { welcome, placeholder, suggestions, accent, accentForeground, wide };
}
