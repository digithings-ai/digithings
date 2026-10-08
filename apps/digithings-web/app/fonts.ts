import { Geist_Mono, Inter } from "next/font/google";

/**
 * digithings.ai font config — the only file in this app that calls next/font.
 *
 * Self-hosted at build time (served from /_next/static/media), so no request
 * ever leaves for fonts.googleapis.com. Both faces are variable fonts: weights
 * come from the axis, not from synthesized bold.
 *
 * SWAP A FACE = change the loader on the line below (plus its import). Every
 * stylesheet reads `--font-sans` / `--font-mono` / `--font-display` from
 * `@digithings/design/tokens.css`, which builds the stacks off the generic
 * `--font-*-face` variables declared here. See "Fonts per surface" in
 * packages/design/README.md.
 */

/** Sans / display voice: nav, headings, prose, form fields. */
export const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans-face",
  display: "swap",
});

/** Mono voice: labels, code, commands, tabular figures. */
export const mono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono-face",
  display: "swap",
});

/** The class the root layout puts on <html>; see the note there about scoping. */
export const fontVariables = `${sans.variable} ${mono.variable}`;