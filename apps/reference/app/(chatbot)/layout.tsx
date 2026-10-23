import "./chatbot-shell.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { themeInitScript } from "@digithings/ui/theme-init";
import { ThemeToggle, ThemeProvider } from "@digithings/ui/theme-provider";

export const metadata: Metadata = {
  title: "digichat gallery",
  description: "Official assistant-ui Thread, themed with digiweb tokens.",
};

export default function ChatbotRootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <meta name="theme-color" content="#0A0E0C" />
      </head>
      <body>
        <ThemeProvider>
          <header className="chatbot-bar">
            <span className="chatbot-bar-mark">digichat</span>
            {/* /chatbot is an isolated root (its own shell + @source graph), so
                it renders no SiteNav — this header link is its way back to the
                gallery index and the rest of the canon. */}
            <Link href="/" className="chatbot-bar-home">
              ← design reference
            </Link>
            <ThemeToggle className="chatbot-theme-toggle" />
          </header>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
