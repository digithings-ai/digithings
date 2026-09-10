/**
 * Gallery stand-in for `chrome.welcome` + `chrome.suggestions` in deploy YAML.
 * Same shape as digichat WelcomeCopySchema. Default: introduce the product.
 * Starters render as example rows immediately above the composer, not chips.
 */
export type GalleryWelcomeCopy = {
  title: string;
  body?: string | readonly string[];
};

export type GalleryWelcomeSuggestion =
  | string
  | { title: string; label?: string; prompt: string };

export const GALLERY_WELCOME: GalleryWelcomeCopy = {
  title: "Ask the stack.",
  body: "It reads the docs, then answers.",
};

/** Opt-in starters — example rows immediately above the composer. */
export const GALLERY_SUGGESTIONS: readonly GalleryWelcomeSuggestion[] = [
  "What is digichat?",
  "How do embeds work?",
  "What is digigraph?",
  "How do digisearch and digivault work?",
  "Backtest trend_xsec on ETH-USD",
];

/** `chrome.placeholder` — same string as config/examples/skins/digichat.yaml */
export const GALLERY_PLACEHOLDER = "Ask digichat…";

export function galleryWelcomeBody(copy: GalleryWelcomeCopy): string[] {
  if (!copy.body) return [];
  return typeof copy.body === "string" ? [copy.body] : [...copy.body];
}
