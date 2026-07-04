import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Fraunces } from "next/font/google";
import { ThemeProvider, MotionProvider, themeInitScript, HashScrollManager } from "@digithings/web";

// Editorial serif for the v7 landing direction — self-hosted by next/font so it
// works under `output: "export"` (no runtime CDN <link>). Mirrors digiquant-web.
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
  metadataBase: new URL("https://digithings.ai"),
  title: "digithings — an open-core agentic stack",
  description:
    "An open-core agentic stack — research, retrieval, and chat behind one supervisor. Self-hosted, BYOK, audit-on by default. No vendor lock-in.",
  icons: { icon: "/favicon-qr.svg" },
  openGraph: {
    title: "digithings — an open-core agentic stack",
    description: "Open-core agentic stack — research, retrieval, chat behind one supervisor. Self-hosted, BYOK, audit-on by default.",
    url: "https://digithings.ai",
    images: ["/design/assets/og.png"],
    type: "website",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  // suppressHydrationWarning: themeInitScript (and the /docs ivory default)
  // legitimately flip data-theme + meta pre-hydration; scoped to this
  // element's attributes only.
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable} ${fraunces.variable} no-js`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        {/* Law 06 (content-first): SSR ships html.no-js so stylesheet rules can
            neutralize JS-gated hiding (hero entrance, [data-motion] reveals);
            removed pre-paint when scripts run. */}
        <script dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.remove('no-js')" }} />
        {/* Single fallback; themeInitScript sets it to the active theme pre-paint. */}
        <meta name="theme-color" content="#0B0C0E" />
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
