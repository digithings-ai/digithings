import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Fraunces } from "next/font/google";
import { ThemeProvider, MotionProvider, themeInitScript, HashScrollManager } from "@digithings/web";

// Editorial serif for the v7 landing direction — self-hosted by next/font so it
// works under `output: "export"` (no runtime CDN <link>). digiquant-local only.
const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  // variable font: `axes` requires weight to be variable (omitted), so the CSS
  // `font-weight: 400/500` selects within the loaded range.
  axes: ["opsz"],
  style: ["normal", "italic"],
  variable: "--font-fraunces",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://digiquant.io"),
  applicationName: "DigiQuant",
  title: "digiquant — a quant research desk in a glass box you own",
  description:
    "The research stack an institutional desk would build — Atlas researches, Hermes sizes the risk, "
    + "and every run writes a decision log under its own run id, redacted on the way out. Open-source "
    + "and self-hosted, so work that once needed a team runs for one.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "DigiQuant",
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
    title: "digiquant — a quant research desk in a glass box you own",
    description:
      "Atlas researches, Hermes sizes the risk, and the deliberation stays on the record. Open-source, "
      + "self-hosted, with a decision log per run.",
    url: "https://digiquant.io",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  // suppressHydrationWarning: themeInitScript legitimately flips data-theme
  // pre-hydration for system-light visitors; scoped to this element only.
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable} ${fraunces.variable} no-js`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        {/* Law 06 (content-first): SSR ships html.no-js so stylesheet rules can
            neutralize JS-gated hiding (hero entrance, [data-motion] reveals,
            the strategy deck); removed pre-paint when scripts run. */}
        <script dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.remove('no-js')" }} />
        {/* Single fallback; themeInitScript sets it to the active theme pre-paint. */}
        <meta name="theme-color" content="#0A0E0C" />{/* canon-allow: tokens.css dark --bg */}
      </head>
      <body>
        <div className="grain" aria-hidden="true" />
        <div className="glow" aria-hidden="true" />
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
