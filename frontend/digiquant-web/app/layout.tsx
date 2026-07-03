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
  title: "digiquant — a quant hedge fund, in a box you own",
  description:
    "The research-to-execution stack an institutional desk would build — Atlas researches, Hermes sizes the risk, Kairos executes. Open-source and self-hosted, so a fund that once needed a team now runs for one.",
  icons: {
    icon: [
      { url: "/favicon-qr-light.svg", media: "(prefers-color-scheme: dark)" },
      { url: "/favicon-qr.svg", media: "(prefers-color-scheme: light)" },
      { url: "/favicon-qr.svg" },
    ],
  },
  openGraph: {
    title: "digiquant — a quant hedge fund, in a box you own",
    description:
      "Atlas researches, Hermes sizes the risk, Kairos executes. Open-source, self-hosted, human-gated.",
    url: "https://digiquant.io",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  // suppressHydrationWarning: themeInitScript legitimately flips data-theme
  // pre-hydration for system-light visitors; scoped to this element only.
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable} ${fraunces.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
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
