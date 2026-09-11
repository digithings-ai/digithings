import "./chatbot-shell.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
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
          <ChatbotThemeToggle />
        </header>
        {children}
      </body>
    </html>
  );
}
