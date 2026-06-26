import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { ThemeProvider, MotionProvider, themeInitScript } from "@digithings/web";

export const metadata: Metadata = {
  metadataBase: new URL("https://digiquant.io"),
  title: "DigiQuant — quant-native AI, on infrastructure you own",
  description:
    "Backtest, optimize, and deploy on NautilusTrader. Atlas researches, Hermes deliberates, Kairos executes — open core, self-hosted, human-gated.",
  icons: {
    icon: [
      { url: "/favicon-qr-light.svg", media: "(prefers-color-scheme: dark)" },
      { url: "/favicon-qr.svg", media: "(prefers-color-scheme: light)" },
      { url: "/favicon-qr.svg" },
    ],
  },
  openGraph: {
    title: "DigiQuant — quant-native AI",
    description: "Research → signals → execution on NautilusTrader. Open core.",
    url: "https://digiquant.io",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        {/* Single fallback; themeInitScript sets it to the active theme pre-paint. */}
        <meta name="theme-color" content="#0B0C0E" />
      </head>
      <body>
        <div className="grain" aria-hidden="true" />
        <div className="glow" aria-hidden="true" />
        <MotionProvider>
          <ThemeProvider>{children}</ThemeProvider>
        </MotionProvider>
      </body>
    </html>
  );
}
