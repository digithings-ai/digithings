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
  return { welcome, placeholder, suggestions, accent, accentForeground };
}
