import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Geist_Mono, IBM_Plex_Mono, Inter } from "next/font/google";
import "../(baseline)/baseline.css";

/** assistant-ui default template fonts (mirrors the baseline shell). */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-ibm-plex-mono",
});

/**
 * The preview pane renders the first-party `digichat` skin, whose theme reads
 * `--font-geist-mono` — borrowed here just like the baseline shell does.
 */
const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
});

export const metadata: Metadata = {
  title: "digichat devkit",
  robots: { index: false, follow: false },
};

/**
 * Isolated root layout: no digichat globals.css, tokens, CLI skin, or Providers.
 * Shares the baseline assistant-ui template sheet — the devkit menu and the
 * saved-file preview both render on stock tokens, never app chrome.
 */
export default function DevkitRootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${ibmPlexMono.variable} ${geistMono.variable} h-full`}
    >
      <body className={`${inter.className} h-full antialiased`}>{children}</body>
    </html>
  );
}
