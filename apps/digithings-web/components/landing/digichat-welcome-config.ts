/**
 * Deploy-shaped welcome copy for the landing-page digichat simulation (#4429).
 *
 * Ported from the design reference's `digichat-welcome-config.ts` (point 13,
 * Stage 8): the reference lives under `apps/reference`, which must not become a
 * runtime dependency of the site, so the three files it needs are copied here
 * and kept byte-faithful where they can be.
 *
 * Shape matches digichat's `WelcomeCopySchema`: a title plus optional body
 * lines, and starters that render as example rows immediately above the
 * composer — not chips, not a top-of-thread empty state.
 *
 * Honesty: this is a *simulation*. The copy says what the box is; it promises
 * no capability that is not shipped and states no figure.
 */
export type WelcomeCopy = {
  title: string;
  body?: string | readonly string[];
};

export type WelcomeSuggestion =
  | string
  | { title: string; label?: string; prompt: string };

/** `chrome.welcome` — the same line pair the gallery Thread renders. */
export const ASK_WELCOME: WelcomeCopy = {
  title: "Ask the stack.",
  body: "It reads the docs, then answers.",
};

/**
 * `chrome.suggestions` — the example rows. Every one of them maps to a docs
 * turn the shipped digisearch + digivault loop can actually answer, so the
 * promised behaviour and the real behaviour agree.
 */
export const ASK_SUGGESTIONS: readonly WelcomeSuggestion[] = [
  "What is digichat?",
  "How do the modules fit together?",
  "How do digisearch and digivault work?",
  "What is not built yet?",
];

/** `chrome.placeholder` — same string as digichat's own skin config. */
export const ASK_PLACEHOLDER = "Ask digichat…";

export function welcomeBody(copy: WelcomeCopy): string[] {
  if (!copy.body) return [];
  return typeof copy.body === "string" ? [copy.body] : [...copy.body];
}
