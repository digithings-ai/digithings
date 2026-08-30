import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { ThemeProvider, MotionProvider, themeInitScript, HashScrollManager } from "@digithings/web";
import { LegacyByokPurge } from "@/components/LegacyByokPurge";

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
// the shared @digithings/web themeInitScript because only this site has /docs.
const docsIvoryInit =
  "try{if(/^\\/docs(\\/|$)/.test(location.pathname)&&!localStorage.getItem('dt-theme')){document.documentElement.setAttribute('data-theme','light');var m=document.querySelector('meta[name=\"theme-color\"]');if(m)m.setAttribute('content','#FBFBF9')}}catch(e){}"; // canon-allow: mirrors tokens.css light --bg (pre-paint script)

export default function RootLayout({ children }: { children: ReactNode }) {
  // suppressHydrationWarning: themeInitScript (and the /docs ivory default)
  // legitimately flip data-theme + meta pre-hydration; scoped to this
  // element's attributes only.
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning className={`${GeistMono.variable} no-js`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
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
        <div className="grain" aria-hidden="true" />
        <div className="glow" aria-hidden="true" />
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
