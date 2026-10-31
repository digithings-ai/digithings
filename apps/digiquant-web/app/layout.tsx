import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { HashScrollManager, MotionProvider, ThemeProvider, faviconThemeScript } from "@digithings/ui";
import { SiteChrome } from "@/components/site-chrome";
import { HERO_PLAYED_SCRIPT } from "@/lib/hero-play";
import { fontVariables } from "./fonts";

export const metadata: Metadata = {
  metadataBase: new URL("https://digiquant.io"),
  applicationName: "digiquant",
  title: "digiquant — a quant research desk in a glass box you own",
  description:
    "A showcase of the digiquant dashboard, the product: the house book, the research pipeline, and the method behind it. "
    + "Research runs daily, portfolio sizes the risk, and every run writes a decision log under its own "
    + "run id, redacted on the way out. Open-source and self-hosted.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "digiquant",
    statusBarStyle: "black-translucent",
  },
  // The page is pinned dark. The script still selects the dark quant tile so an
  // OS light scheme cannot swap in the light file before paint.
  icons: {
    icon: [
      { url: "/icons/digi-app-dark.svg", type: "image/svg+xml" },
      { url: "/favicon.ico", sizes: "48x48" },
      { url: "/icons/digi-app-32.png", type: "image/png", sizes: "32x32" },
    ],
    shortcut: "/favicon.ico",
    apple: [{ url: "/icons/digi-app-touch-dark.png", type: "image/png", sizes: "180x180" }],
  },
  openGraph: {
    title: "digiquant — a quant research desk in a glass box you own",
    description:
      "See the digiquant dashboard at work: the house book, how a strategy is built, and the "
      + "tooling underneath. Open-source, self-hosted, with a decision log per run.",
    url: "https://digiquant.io",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "digiquant — a quant research desk in a glass box you own.",
      },
    ],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "digiquant — a quant research desk in a glass box you own",
    images: ["/og.png"],
  },
};

const faviconInit = faviconThemeScript({
  dark: "/icons/digi-app-dark.svg",
  light: "/icons/digi-app-light.svg",
  touchDark: "/icons/digi-app-touch-dark.png",
  touchLight: "/icons/digi-app-touch-light.png",
});

export default function RootLayout({ children }: { children: ReactNode }) {
  // suppressHydrationWarning: the inline script sets data-theme before hydration;
  // scoped to this element only.
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning className={`${fontVariables} accent-digiquant no-js`}>
      <head>
        {/* One solid black canvas: the page is pinned to the dark theme, so the
            system-light flip themeInitScript does is deliberately not used. */}
        <script dangerouslySetInnerHTML={{ __html: "document.documentElement.setAttribute('data-theme','dark')" }} />
        <script dangerouslySetInnerHTML={{ __html: faviconInit }} />
        {/* Law 06 (content-first): SSR ships html.no-js so stylesheet rules can
            neutralize JS-gated hiding (hero entrance, [data-motion] reveals,
            the strategy deck); removed pre-paint when scripts run. */}
        <script dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.remove('no-js')" }} />
        {/* Later loads in this tab skip the secondary pixel-mark rise. The top hero builds on every load. */}
        <script dangerouslySetInnerHTML={{ __html: HERO_PLAYED_SCRIPT }} />
        
        <meta name="theme-color" content="#000000" />{/* canon-allow: page canvas is solid black, see globals.css */}
      </head>
      <body>
        <MotionProvider>
          <ThemeProvider>
            <HashScrollManager />
            <SiteChrome>{children}</SiteChrome>
          </ThemeProvider>
        </MotionProvider>
      </body>
    </html>
  );
}
