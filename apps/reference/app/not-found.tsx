import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { ThemeProvider, themeInitScript } from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";

/**
 * The reference app renders two root layouts — the (gallery) canon and the
 * isolated (chatbot) shell — so an unmatched URL has no single layout to
 * inherit. This not-found carries the canon's own document (the same
 * globals.css tokens, mono/serif pairing and `.reference-page` scaffold) and
 * offers the two ways back the audit asked for: the gallery index and the
 * family map (anchored at `#contents` on the home page).
 */
export const metadata: Metadata = {
  title: "No such page — design reference",
  description: "The address does not match any page in the frontend design reference.",
};

export default function NotFound() {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <meta name="theme-color" content="#0A0E0C" />{/* canon-allow: tokens.css dark --bg */}
      </head>
      <body>
        <ThemeProvider>
          <main className="reference-page">
            <header className="hero">
              <p className="kicker">{"// 404"}</p>
              <h1>
                No such <em>page.</em>
              </h1>
              <p>
                The address does not match anything in the design reference. The gallery
                index is the fastest way back; the family map lists every page the canon
                ships.
              </p>
            </header>

            <div className="btn-row">
              <Link className={buttonVariants({ variant: "default" })} href="/">
                Gallery index
              </Link>
              <Link className={buttonVariants({ variant: "outline" })} href="/#contents">
                Family map
              </Link>
            </div>
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
