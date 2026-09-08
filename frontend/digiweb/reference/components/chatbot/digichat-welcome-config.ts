/**
 * Gallery stand-in for `chrome.welcome` + `chrome.suggestions` in deploy YAML.
 * Same shape as digichat WelcomeCopySchema. Default: introduce the product,
 * no starter chips. Clients add chips in config when they want them.
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

/** Empty on purpose: starters are opt-in via deploy config. */
export const GALLERY_SUGGESTIONS: readonly GalleryWelcomeSuggestion[] = [];

/** `chrome.placeholder` — same string as config/examples/skins/digichat.yaml */
export const GALLERY_PLACEHOLDER = "Ask digichat…";

export function galleryWelcomeBody(copy: GalleryWelcomeCopy): string[] {
  if (!copy.body) return [];
  return typeof copy.body === "string" ? [copy.body] : [...copy.body];
}
