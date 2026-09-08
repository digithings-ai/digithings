/**
 * Gallery stand-in for `chrome.welcome` + `chrome.suggestions` in deploy YAML.
 * Same shape as digichat WelcomeCopySchema. Default: introduce the product.
 * Starters render as a `>` list above the composer, not chips.
 */
export type GalleryWelcomeCopy = {
  title: string;
  body?: string | readonly string[];
};

export type GalleryWelcomeSuggestion =
  | string
  | { title: string; label?: string; prompt: string };

export const GALLERY_WELCOME: GalleryWelcomeCopy = {
  title: "digichat",
  body: "The chat surface for this stack. Scoped to the tools and data in this deployment — not a general-purpose chatbot.",
};

/** Opt-in starters — `>` lines immediately above the composer. */
export const GALLERY_SUGGESTIONS: readonly GalleryWelcomeSuggestion[] = [
  "backtest ETH-USD",
  "what can this deployment do?",
];

/** `chrome.placeholder` — same string as config/examples/skins/digichat.yaml */
export const GALLERY_PLACEHOLDER = "Ask digichat…";

export function galleryWelcomeBody(copy: GalleryWelcomeCopy): string[] {
  if (!copy.body) return [];
  return typeof copy.body === "string" ? [copy.body] : [...copy.body];
}
