import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Instrument_Serif } from "next/font/google";
import { ThemeProvider, MotionProvider, themeInitScript } from "@digithings/web";

const serif = Instrument_Serif({ weight: "400", subsets: ["latin"], variable: "--font-instrument", display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL("https://digithings.ai"),
  title: "digithings — an open-core agentic stack",
  description:
    "An open-core, modular agentic stack — composable services wired into one platform. Self-hosted, BYOK, audit-on by default.",
  icons: { icon: "/favicon-qr.svg" },
  openGraph: {
    title: "DigiThings — An open-core agentic stack",
    description: "Composable services, wired into one platform. Open core.",
    url: "https://digithings.ai",
    images: ["/design/assets/og.png"],
    type: "website",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={`${GeistSans.variable} ${GeistMono.variable} ${serif.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <meta name="theme-color" content="#0B0C0E" media="(prefers-color-scheme: dark)" />
        <meta name="theme-color" content="#FBFBF9" media="(prefers-color-scheme: light)" />
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
