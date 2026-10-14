/**
 * The `/chat` surface's first-paint copy, in one place.
 *
 * These strings used to live inside `components/ChatEmbedShell.tsx`, which put
 * them out of reach of anything that is not the embed shell — and the landing
 * page's FAQ band mounts the *same* conversation as a small in-page thread, so it
 * needed the same welcome and the same examples. Two copies of "what digichat
 * says when it opens" is exactly the kind of drift that leaves a visitor reading
 * one set of examples in the cube and a different set after expanding it.
 *
 * So the copy moved here, `ChatEmbedShell` re-exports it for its existing
 * importers, and `digichat-welcome-config.ts` reads the same record. One source,
 * one answer.
 *
 * The host constants live here too because the record is keyed by them; the
 * contract test that pins their values (`ChatEmbedShell.contract.test.ts`) is
 * unchanged.
 */

/** Default embed host for digithings.ai/chat (client #0). */
export const DEFAULT_CHAT_EMBED_HOST = "digithings.ai";

/** Virtual first-party host for digithings.ai/chat/occ (client #1). */
export const OCC_CHAT_EMBED_HOST = "occ.digithings.ai";

/**
 * Curated first-paint copy per host: the boot loader types it while the
 * container wakes, and the same strings ride the iframe URL so the ready hero
 * matches the loader it replaces. Keep every example a single line — the chips
 * render one row each.
 */
export const EMBED_SHELL_COPY: Record<
  string,
  { welcome: string; suggestions: string[] }
> = {
  [DEFAULT_CHAT_EMBED_HOST]: {
    welcome: "Ask about digithings",
    suggestions: [
      "What is digigraph?",
      "Search the docs for NautilusTrader",
      "How do I run the stack locally?",
      "Summarize the digithings architecture",
    ],
  },
  [OCC_CHAT_EMBED_HOST]: {
    welcome: "Ask about Online Compliance Center",
    suggestions: [
      "How do I file a support ticket?",
      "Search the help articles for onboarding",
      "Show my open Zammad tickets",
      "What is our data retention policy?",
    ],
  },
};
