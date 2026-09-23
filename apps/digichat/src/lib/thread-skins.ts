/**
 * Official assistant-ui templates a digichat container can pick at deploy time.
 *
 * Ids 1–11 match assistant-ui `list_templates`. `digichat` is the first-party
 * Thread — the gallery `/chatbot` module at `@digithings/ui/chat/thread`
 * (`thread.aui.tsx` + slots + cube glyphs), not a catalog clone.
 * `base` is the fixed Base demo. `base-assistant-ui` is the configurable
 * Base shell (brandTheme + labels). Same Thread, different catalog product.
 *
 * They are vendored in the image — not a CDN switch and not shadcn styles.
 */

import type { CSSProperties } from "react";

export const THREAD_SKINS = [
  "base",
  "chatgpt",
  "claude",
  "grok",
  "gemini",
  "perplexity",
  "react-ink",
  "expo-react-native",
  "base-assistant-ui",
  "webpage-assistant",
  "product-page-assistant",
  "digichat",
] as const;

export type ThreadSkin = (typeof THREAD_SKINS)[number];

export const DEFAULT_THREAD_SKIN: ThreadSkin = "base";

/** First-party marketing / OCC hosts. Unset `skin` → `digichat`, not catalog `base`. */
export const FIRST_PARTY_DEFAULT_SKIN_HOSTS: ReadonlySet<string> = new Set([
  "digithings.ai",
  "www.digithings.ai",
  "occ.digithings.ai",
]);

export const FIRST_PARTY_DEFAULT_SKIN_SLUGS: ReadonlySet<string> = new Set([
  "digithings",
  "digithings-ai",
  "occ",
]);

/**
 * Runtime default for a tenant host/slug when YAML / DIGICHAT_EMBED_TENANTS
 * omit `skin`. Third-party tenants stay on catalog `base`. Explicit `skin`
 * must still win at the call site.
 */
export function defaultThreadSkinForTenant(opts: {
  host?: string | null;
  slug?: string | null;
  aliases?: readonly string[] | null;
}): ThreadSkin {
  const hosts = [opts.host, ...(opts.aliases ?? [])];
  for (const raw of hosts) {
    const host = raw?.trim().toLowerCase().split("/")[0].split(":")[0].replace(/\.$/, "");
    if (host && FIRST_PARTY_DEFAULT_SKIN_HOSTS.has(host)) return "digichat";
  }
  const slug = opts.slug?.trim().toLowerCase();
  if (slug && FIRST_PARTY_DEFAULT_SKIN_SLUGS.has(slug)) return "digichat";
  return DEFAULT_THREAD_SKIN;
}

export const CLONE_SKINS = [
  "chatgpt",
  "claude",
  "grok",
  "gemini",
  "perplexity",
] as const;

export type CloneSkin = (typeof CLONE_SKINS)[number];

/**
 * Catalog templates that own the viewport (docs shell, product dashboard,
 * Expo phone frame). Host chrome (ChatShell CLI, embed header, memory
 * sidebar) must not wrap these — the template is the page.
 */
export const LAYOUT_SKINS = [
  "webpage-assistant",
  "product-page-assistant",
  "expo-react-native",
] as const;

export type LayoutSkin = (typeof LAYOUT_SKINS)[number];

/**
 * The ink a skin paints its own text with, so the credit sitting inside that
 * skin's DOM stays legible instead of matching the canvas.
 *
 * The catalog skins carry their palette as Tailwind classes on their own root
 * element (`text-[#0d0d0d] dark:text-[#ececec]`, `text-[#1a1a18]`, …), not as
 * a scoped CSS variable, and `ThreadPrimitive.Root` hard-codes
 * `data-thread-skin="digichat"` for every skin — so there is nothing per-skin
 * to inherit. These literals mirror the skin roots' *text* colour; keep them in
 * step when a skin's palette changes. A skin with no entry (`base`, `digichat`,
 * layout skins) falls through to `--muted-foreground`, which those skins
 * already theme correctly.
 *
 * Never map this to the canvas colour: white ink on a white canvas is exactly
 * the invisible-credit bug the review caught on the clone skins.
 */
const SKIN_INK: Partial<Record<ThreadSkin, { light: string; dark: string }>> = {
  // canon-allow: each line mirrors a catalog skin's own Tailwind text colour
  // (`text-[#0d0d0d] dark:text-[#ececec]`, `text-[#1a1a18]`, …). There is no kit
  // token for a third-party palette, and they exist only so the credit stays
  // legible inside the skin.
  chatgpt: { light: "#0d0d0d", dark: "#ececec" }, // canon-allow
  claude: { light: "#1a1a18", dark: "#eee" }, // canon-allow
  grok: { light: "#0d0d0d", dark: "#ececec" }, // canon-allow
  gemini: { light: "#1f1f1f", dark: "#e3e3e3" }, // canon-allow
  perplexity: { light: "#1f1b17", dark: "#f5f2ed" }, // canon-allow
};

/**
 * Ink for the credit line, as an inline custom property.
 *
 * Returns `{}` for a skin with no literal ink (`base`, `digichat`, layout
 * skins), leaving `.dc-attribution` to its `--muted-foreground` fallback.
 */
export function skinCreditStyle(
  skin: ThreadSkin,
  theme: "light" | "dark",
): CSSProperties {
  const ink = SKIN_INK[skin];

  if (!ink) return {};

  return { "--credit-ink": ink[theme] } as CSSProperties;
}

export function threadSkinChoices(): string {
  return THREAD_SKINS.join(", ");
}

export function isThreadSkin(value: unknown): value is ThreadSkin {
  return typeof value === "string" && (THREAD_SKINS as readonly string[]).includes(value);
}

export function isCloneSkin(value: ThreadSkin): value is CloneSkin {
  return (CLONE_SKINS as readonly string[]).includes(value);
}

export function skinOwnsPageChrome(value: ThreadSkin): boolean {
  return (LAYOUT_SKINS as readonly string[]).includes(value);
}

export const FRAMED_CHROME_MODES = ["modal", "sidebar"] as const;
export type FramedChromeMode = (typeof FRAMED_CHROME_MODES)[number];

/**
 * True for the modes that mount the chat inside a frame rather than the page.
 *
 * Lives here, not in `components/stock/presentation-frame.tsx`: that module is
 * `"use client"`, and `app/(digichat)/page.tsx` is a server component, so
 * importing the predicate from there made the server *invoke* a client function
 * at render time ("Attempted to call isFramedPresentation() from the server but
 * isFramedPresentation is on the client"). This module is plain, so both sides
 * can share one definition of the invariant.
 */
export function isFramedPresentation(mode: string): mode is FramedChromeMode {
  return (FRAMED_CHROME_MODES as readonly string[]).includes(mode);
}

/** Parse a query/env/YAML value; unknown → default. */
export function parseThreadSkin(
  value: string | null | undefined,
  fallback: ThreadSkin = DEFAULT_THREAD_SKIN,
): ThreadSkin {
  const trimmed = value?.trim().toLowerCase();
  return isThreadSkin(trimmed) ? trimmed : fallback;
}
