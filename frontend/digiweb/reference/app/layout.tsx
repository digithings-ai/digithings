import "./globals.css";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import {
  Bricolage_Grotesque,
  Fraunces,
  IBM_Plex_Mono,
  IBM_Plex_Sans,
  IBM_Plex_Serif,
  JetBrains_Mono,
  Newsreader,
} from "next/font/google";
import { ThemeProvider, MotionProvider, themeInitScript } from "@digithings/web";
import { SiteNav } from "@/components/site-nav";
import { liveryInitScript } from "@/components/livery-store";
import { typeInitScript } from "@/components/type-store";

const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  axes: ["opsz"],
  style: ["normal", "italic"],
  variable: "--font-fraunces",
});

// Candidate faces for the live type-suite switcher (type-store). Each suite
// coordinates display + body + mono; the IBM Plex trio is a true superfamily.
const plexSerif = IBM_Plex_Serif({
  subsets: ["latin"],
  weight: ["400", "600"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-plex-serif",
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-plex-sans",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-plex-mono",
});

const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-newsreader",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jetbrains",
});

const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-bricolage",
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
      className={`${GeistSans.variable} ${GeistMono.variable} ${fraunces.variable} ${plexSerif.variable} ${plexSans.variable} ${plexMono.variable} ${newsreader.variable} ${jetbrains.variable} ${bricolage.variable} no-js`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: liveryInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: typeInitScript }} />
        <script
          dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.remove('no-js')" }}
        />
        <meta name="theme-color" content="#0A0E0C" />{/* canon-allow: tokens.css dark --bg */}
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
