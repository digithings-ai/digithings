import { Geist_Mono, Inter } from "next/font/google";

/**
 * digiquant.io font config — the only file in this app that calls next/font.
 *
 * Self-hosted at build time, so no request leaves for Google at runtime. Same
 * pairing as digithings.ai.
 *
 * SWAP A FACE = change the loader on the line below (plus its import). Every
 * stylesheet reads `--font-sans` / `--font-mono` / `--font-display` from
 * `@digithings/design/tokens.css`, which builds the stacks off the generic
 * `--font-*-face` variables declared here. See "Fonts per surface" in
 * packages/design/README.md.
 */

/** Sans / display voice: headings, prose. */
export const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans-face",
  display: "swap",
});

/** Chrome voice: labels, code, figures. */
export const mono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono-face",
  display: "swap",
});

/** The class the root layout puts on <html>. */
export const fontVariables = `${sans.variable} ${mono.variable}`;