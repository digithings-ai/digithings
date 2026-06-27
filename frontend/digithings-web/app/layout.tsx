import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Fraunces } from "next/font/google";
import { ThemeProvider, MotionProvider, themeInitScript } from "@digithings/web";

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
    <html lang="en" data-theme="dark" className={`${GeistSans.variable} ${GeistMono.variable} ${fraunces.variable}`}>
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
