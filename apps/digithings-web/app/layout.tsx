import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ThemeProvider, MotionProvider, themeInitScript, HashScrollManager, LayoutLines } from "@digithings/ui";
import { LegacyByokPurge } from "@/components/LegacyByokPurge";

// Self-hosted at build time by next/font (served from /_next/static/media), so no
// request ever leaves for fonts.googleapis.com. Inter is the sans/display voice
// (nav, headings, prose, form fields); JetBrains Mono is the mono voice (labels,
// code, commands, tabular figures). Both are variable fonts: weights come from the
// axis, not from synthesized bold.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://digithings.ai"),
  applicationName: "digithings",
  title: "digithings — AI infrastructure in a glass box",
  description:
    "Open-source, MIT-licensed AI infrastructure: nine modules that plug into the stack you already "
    + "run — not a replacement for it. Self-hosted anywhere, your own keys and providers, every step "
    + "traceable.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "digithings",
    statusBarStyle: "black-translucent",
  },
  // Cache-busting paths ensure browsers leave the retired QR mark behind.
  // Tabs follow the OS scheme; install/touch PNGs use the same compact `d` +
  // cursor artwork rather than a browser-generated initial.
  icons: {
    icon: [
      { url: "/icons/digi-app-dark.svg", type: "image/svg+xml", media: "(prefers-color-scheme: dark)" },
      { url: "/icons/digi-app-light.svg", type: "image/svg+xml", media: "(prefers-color-scheme: light)" },
      { url: "/icons/digi-app-32.png", type: "image/png", sizes: "32x32" },
    ],
    shortcut: "/icons/digi-app-32.png",
    apple: [
      { url: "/icons/digi-app-touch-dark.png", type: "image/png", sizes: "180x180", media: "(prefers-color-scheme: dark)" },
      { url: "/icons/digi-app-touch-light.png", type: "image/png", sizes: "180x180", media: "(prefers-color-scheme: light)" },
    ],
  },
  openGraph: {
    title: "digithings — AI infrastructure in a glass box",
    description:
      "Open-source AI infrastructure you self-host: nine MIT-licensed modules that drop into the "
      + "stack you already run. Your own keys and providers, every step traceable.",
    url: "https://digithings.ai",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "digithings — AI infrastructure in a glass box you own.",
      },
    ],
    type: "website",
  },
};

// /docs defaults to the ivory reading mode (canon §14: long-form surfaces go
// light) unless the visitor has chosen a theme (dt-theme). This used to live as
// an inline <script> in the /docs *segment* layout, but a script rendered by a
// route segment is re-created (not hydrated) on every client-side navigation
// into /docs — which makes React 19 warn ("Encountered a script tag while
// rendering React component…") and, because client-created scripts never
// execute, the ivory default only ever applied on a hard load anyway. Running
// it here in the always-hydrated pre-paint <head> keeps the hard-load ivory
// default (no flash) and removes the warning; the pathname guard scopes it to
// /docs (trailingSlash export → /docs/ also matches). Kept local rather than in
// the shared @digithings/ui themeInitScript because only this site has /docs.
const docsIvoryInit =
  "try{if(/^\\/docs(\\/|$)/.test(location.pathname)&&!localStorage.getItem('dt-theme')){document.documentElement.setAttribute('data-theme','light');var m=document.querySelector('meta[name=\"theme-color\"]');if(m)m.setAttribute('content','#FBFBF9')}}catch(e){}"; // canon-allow: mirrors tokens.css light --bg (pre-paint script)

// Global pre-paint: apply the stored choice on every route. The SSR default is
// dark; without this a visitor whose stored theme is light paints dark first
// and flips to light only at hydration (~0.5s in) - the load flash. Mirrors
// the toggle's storage key (dt-theme).
const storedThemeInit =
  "try{var t=localStorage.getItem('dt-theme');if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t);if(t==='light'){var m=document.querySelector('meta[name=\"theme-color\"]');if(m)m.setAttribute('content','#FBFBF9')}}}catch(e){}"; // canon-allow: mirrors tokens.css light --bg (pre-paint script)

export default function RootLayout({ children }: { children: ReactNode }) {
  // suppressHydrationWarning: themeInitScript (and the /docs ivory default)
  // legitimately flip data-theme + meta pre-hydration; scoped to this
  // element's attributes only.
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning className={`${inter.variable} ${jetbrainsMono.variable} no-js`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        {/* Stored theme choice (all routes) — pre-paint so no dark→light flip at hydration. */}
        <script dangerouslySetInnerHTML={{ __html: storedThemeInit }} />
        {/* /docs → ivory default (pre-paint), scoped by pathname; see docsIvoryInit above. */}
        <script dangerouslySetInnerHTML={{ __html: docsIvoryInit }} />
        {/* Law 06 (content-first): SSR ships html.no-js so stylesheet rules can
            neutralize JS-gated hiding (hero entrance, [data-motion] reveals);
            removed pre-paint when scripts run. */}
        <script dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.remove('no-js')" }} />
        {/* Single fallback; themeInitScript sets it to the active theme pre-paint.
            Literal = tokens.css dark --bg (metas can't read CSS vars). */}
        <meta name="theme-color" content="#0A0E0C" />{/* canon-allow: tokens.css dark --bg */}
      </head>
      <body>
        {/* One pair for every route. Above page paint so a full-bleed
            surface still shows the rails; under the nav (z-index 210).
            DocumentFrame also mounts a pair — the style hides that copy.
            A style tag, not globals.css: Tailwind rewrites a `.line-y`
            selector because `line-y` is an `@utility`. */}
        <LayoutLines className="site-rails z-20" />
        <style>{":not(.site-rails) > .line-y{display:none}"}</style>
        <LegacyByokPurge />
        <MotionProvider>
          <ThemeProvider>
            <HashScrollManager />
            {children}
          </ThemeProvider>
        </MotionProvider>
      </body>
    </html>
  );
}
