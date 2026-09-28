import "./chatbot-shell.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import {
  ChatbotThemeToggle,
  chatbotThemeInitScript,
} from "@/components/chatbot/chatbot-theme";

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
        <script dangerouslySetInnerHTML={{ __html: chatbotThemeInitScript }} />
        <meta name="theme-color" content="#0A0E0C" />
      </head>
      <body>
        <header className="chatbot-bar">
          <span className="chatbot-bar-mark">digichat</span>
          {/* /chatbot is an isolated root (its own shell + @source graph), so
              it renders no SiteNav — this header link is its way back to the
              gallery index and the rest of the canon. */}
          <Link href="/" className="chatbot-bar-home">
            ← design reference
          </Link>
          <ChatbotThemeToggle />
        </header>
        {children}
      </body>
    </html>
  );
}
