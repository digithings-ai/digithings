import { Geist_Mono, Inter } from "next/font/google';

/**
 * digiquant app font config — the only file in this app that calls next/font.
 *
 * This surface keeps its own hand-rolled palette (it does not load
 * `@digithings/design/tokens.css`), so `app/globals.css` builds `--sans` and
 * `--mono` straight off the generic `--font-*-face` variables declared here.
 * `packages/design/tokens.css` builds the same two stacks for every other
 * surface, from the same variable names.
 *
 * SWAP A FACE = change the loader on the line below (plus its import). See
 * "Fonts per surface" in packages/design/README.md.
 */

/** Prose voice. */
export const sans = Inter({
  subsets: ['latin'],
  variable: '--font-sans-face',
  display: 'swap',
});

/**
 * Chrome + figures voice. The digiquant.io wordmark is this same face, so the
 * logo word and the figures share one loaded file.
 */
export const mono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-mono-face',
  display: 'swap',
});

/** The class the root layout puts on <html>. */
export const fontVariables = `${sans.variable} ${mono.variable}`;