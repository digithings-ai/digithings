import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Fraunces } from "next/font/google";
import { ThemeProvider, MotionProvider, themeInitScript } from "@digithings/web";
import { SiteNav } from "@/components/site-nav";
import { liveryInitScript } from "@/components/livery-store";

const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  axes: ["opsz"],
  style: ["normal", "italic"],
  variable: "--font-fraunces",
});

export const metadata: Metadata = {
  title: "digithings frontend design reference",
  description: "React + Tailwind + Motion design reference for digithings frontends.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable} ${fraunces.variable} no-js`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: liveryInitScript }} />
        <script
          dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.remove('no-js')" }}
        />
        <meta name="theme-color" content="#0B0C0E" />
      </head>
      <body>
        <MotionProvider>
          <ThemeProvider>
            <a className="skip-link" href="#main">
              Skip to content
            </a>
            <SiteNav />
            <div id="main">{children}</div>
          </ThemeProvider>
        </MotionProvider>
      </body>
    </html>
  );
}
