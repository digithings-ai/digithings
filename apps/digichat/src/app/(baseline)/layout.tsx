import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Geist_Mono, IBM_Plex_Mono, Inter } from "next/font/google";
import "./baseline.css";

/** assistant-ui default template fonts. */
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
 * The first-party `digichat` skin is part of the catalog and carries its whole
 * theme off `[data-thread-skin="digichat"]` (chat-aui.css → chatbot.css), which
 * resolves `--font-geist-mono`. Without the variable the font declaration is
 * invalid and the skin inherits the page sans — so the catalog loaded it to
 * match the embed and production, which both get it from the digichat layout.
 */
const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
});

export const metadata: Metadata = {
  title: "assistant-ui baseline",
  robots: { index: false, follow: false },
};

/**
 * Isolated root layout: no digichat globals.css, tokens, CLI skin, or Providers.
 * CSS is the official assistant-ui default template sheet. The one nod to the
 * app shell is `--font-geist-mono`, so the catalog's first-party `digichat`
 * skin renders with the same font as the embed.
 */
export default function BaselineRootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${ibmPlexMono.variable} ${geistMono.variable} h-full`}
    >
      <body className={`${inter.className} h-full antialiased`}>{children}</body>
    </html>
  );
}
