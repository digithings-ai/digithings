/**
 * Deploy-shaped welcome copy for the landing-page digichat simulation (#4429).
 *
 * The FAQ band mounts the *same* conversation `/chat` does, one size smaller —
 * the owner's "it's basically using the same container, the same configuration,
 * just displayed in a smaller embedded window… I'd use the same welcome message
 * and examples as in the chat page". So the welcome and the examples are read
 * from the same record the embed shell puts on the iframe URL
 * (`lib/embedCopy.ts`), rather than kept as a second copy that could drift.
 *
 * Round 4 replaced the band's own strings (a title "Ask the stack." and four
 * examples written for digisearch and digivault) with those. A visitor now sees
 * the same four openers before and after expanding, which is the whole point of
 * calling the two surfaces the same thing.
 *
 * Shape matches digichat's `WelcomeCopySchema`: a title plus optional body
 * lines, and starters that render as example rows immediately above the
 * composer — not chips, not a top-of-thread empty state.
 *
 * Honesty: this is a *simulation*, and the answers it streams are canned. The
 * copy says what the box is; it promises no capability that is not shipped and
 * states no figure.
 */
import { DEFAULT_CHAT_EMBED_HOST, EMBED_SHELL_COPY } from "@/lib/embedCopy";

export type WelcomeCopy = {
  title: string;
  body?: string | readonly string[];
};

export type WelcomeSuggestion =
  | string
  | { title: string; label?: string; prompt: string };

/** The shared first-paint copy for the host the landing page embeds. */
const SHELL_COPY = EMBED_SHELL_COPY[DEFAULT_CHAT_EMBED_HOST];

/** `chrome.welcome` — the same line the `/chat` hero opens with. */
export const ASK_WELCOME: WelcomeCopy = {
  title: SHELL_COPY.welcome,
};

/**
 * `chrome.suggestions` — the same example rows `/chat` opens with. Every one is
 * a docs turn the shipped stack can answer, so the promised behaviour and the
 * real behaviour agree.
 */
export const ASK_SUGGESTIONS: readonly WelcomeSuggestion[] = SHELL_COPY.suggestions;

/** `chrome.placeholder` — same string as digichat's own skin config. */
export const ASK_PLACEHOLDER = "Ask digichat…";

export function welcomeBody(copy: WelcomeCopy): string[] {
  if (!copy.body) return [];
  return typeof copy.body === "string" ? [copy.body] : [...copy.body];
}
