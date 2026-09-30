import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import {
  FooterCells,
  HashScrollManager,
  MotionProvider,
  NavShell,
  ThemeProvider,
  themeInitScript,
} from "@digithings/ui";
import { Brand, DQ_FOOTER_CELLS, DQ_FOOTER_META, DQ_NAV_PRIMARY } from "./_nav";

export const metadata: Metadata = {
  metadataBase: new URL("https://digiquant.io"),
  applicationName: "digiquant",
  title: "digiquant — a quant research desk in a glass box you own",
  description:
    "The research stack an institutional desk would build — research runs daily, portfolio sizes the risk, "
    + "and every run writes a decision log under its own run id, redacted on the way out. Open-source "
    + "and self-hosted, so work that once needed a team runs for one.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "digiquant",
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
      "Research runs daily, portfolio sizes the risk, and the deliberation stays on the record. Open-source, "
      + "self-hosted, with a decision log per run.",
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
};

export default function RootLayout({ children }: { children: ReactNode }) {
  // suppressHydrationWarning: themeInitScript legitimately flips data-theme
  // pre-hydration for system-light visitors; scoped to this element only.
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning className={`${GeistMono.variable} no-js`}>
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
        <MotionProvider>
          <ThemeProvider>
            <HashScrollManager />
            <NavShell
              brand={<Brand />}
              links={DQ_NAV_PRIMARY}
              homeLabel="digiquant home"
              skipTo="#main"
            />
            {/* NavShell is fixed: reserve its height (nav-shell.css knob, 62px fallback). */}
            <div className="pt-[var(--nav-shell-h,62px)]">{children}</div>
            <FooterCells cells={DQ_FOOTER_CELLS} meta={DQ_FOOTER_META} />

          </ThemeProvider>
        </MotionProvider>
      </body>
    </html>
  );
}
