import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./baseline.css";
import { fontVariables, sans } from "@/app/fonts";

export const metadata: Metadata = {
  title: "assistant-ui baseline",
  robots: { index: false, follow: false },
};

/**
 * Isolated root layout: no digichat globals.css, tokens, CLI skin, or Providers.
 * CSS is the official assistant-ui default template sheet. Fonts come from the
 * one app font config (`src/app/fonts.ts`) plus the stack aliases in
 * `digichat-app-theme.css`, so the catalog's first-party `digichat` skin renders
 * with the same font as the embed.
 */
export default function BaselineRootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`${fontVariables} h-full`}
    >
      <body className={`${sans.className} h-full antialiased`}>{children}</body>
    </html>
  );
}
