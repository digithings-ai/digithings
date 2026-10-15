import { Geist_Mono } from "next/font/google";

/**
 * digithings.ai font config — the only file in this app that calls next/font.
 *
 * Self-hosted at build time. One mono voice (Chris, 14 Oct 2026): Geist Mono
 * serves display, body and chrome. This replaces the two-face lock from
 * pull request 4898.
 *
 * Stylesheets read `--font-sans` / `--font-mono` / `--font-display` from
 * `@digithings/design/tokens.css`, which builds the stacks off `--font-mono-face`.
 */

/** The one voice: display, prose, labels, code, figures. */
export const mono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono-face",
  display: "swap",
});

/** The class the root layout puts on <html>. */
export const fontVariables = mono.variable;
