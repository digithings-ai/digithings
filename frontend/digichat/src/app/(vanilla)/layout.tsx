import type { Metadata } from "next";
import type { ReactNode } from "react";
import { IBM_Plex_Mono, Inter } from "next/font/google";
import "./vanilla.css";

/** assistant-ui default template fonts — not Geist / digichat. */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-ibm-plex-mono",
});

export const metadata: Metadata = {
  title: "assistant-ui vanilla",
  robots: { index: false, follow: false },
};

/**
 * Isolated root layout: no digichat globals.css, tokens, CLI skin, or Providers.
 * CSS is the official assistant-ui default template sheet.
 */
export default function VanillaRootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${ibmPlexMono.variable} h-full`}>
      <body className={`${inter.className} h-full antialiased`}>{children}</body>
    </html>
  );
}
