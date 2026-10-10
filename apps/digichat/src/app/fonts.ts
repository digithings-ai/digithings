import { Geist_Mono, Inter } from "next/font/google";

/**
 * digichat font config — the only file in this app that calls next/font.
 *
 * Both the product surface (`(digichat)`) and the catalog skins (`(baseline)`)
 * load their font variables from here, so the whole gallery ships one Geist Mono
 * face. The stacks themselves live in
 * `packages/ui/src/styles/digichat-app-theme.css` — the one stylesheet both
 * route groups are allowed to import — because baseline-isolation forbids
 * baseline.css from importing anything else out of `@digithings/ui`, and that
 * rules out `@digithings/design/tokens.css` here too.
 *
 * SWAP A FACE = change the loader on the line below (plus its import). See
 * "Fonts per surface" in packages/design/README.md.
 */

/** Sans / prose voice. Catalog skins set it on the document body. */
export const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans-face",
  display: "swap",
});

/** Mono / chrome voice, shared by the digichat skin and every catalog skin. */
export const mono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono-face",
  display: "swap",
});

/** The class the host layouts put on <html>. */
export const fontVariables = `${sans.variable} ${mono.variable}`;