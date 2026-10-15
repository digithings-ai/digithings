import { Geist_Mono } from 'next/font/google';

/**
 * dashboard font config — the only file in this app that calls next/font.
 *
 * Self-hosted at build time (served from /dashboard/_next/static/media), so it
 * satisfies the dashboard CSP (font-src 'self' data:) — no fonts.googleapis.com.
 * BLEND v0.1: one mono voice for display, body, and chrome, so there is one
 * loader and one face variable here.
 *
 * SWAP A FACE = change the loader on the line below (plus its import). Every
 * stylesheet reads `--font-sans` / `--font-mono` / `--font-display` from
 * `@digithings/design/tokens.css`, which builds the stacks off the generic
 * `--font-*-face` variable declared here. See "Fonts per surface" in
 * packages/design/README.md.
 */
export const mono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-mono-face',
  display: 'swap',
});

/** The class the root layout puts on <html>; see the note there about scoping. */
export const fontVariables = mono.variable;