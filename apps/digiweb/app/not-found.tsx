import type { Metadata } from "next";
import Link from "next/link";
import { buttonVariants } from "@digithings/ui/ui";

/**
 * The app has one root layout now, so an unmatched URL inherits the shared
 * document, nav and theme straight from `app/layout.tsx` — this file is only
 * the page body.
 */
export const metadata: Metadata = {
  title: "No such page — digiweb",
  description: "The address does not match any page in the digiweb design reference.",
};

export default function NotFound() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// 404"}</p>
        <h1>
          No such <em>page.</em>
        </h1>
        <p>
          The address does not match anything in digiweb. The reference index is the fastest way
          back; the contents map lists every page the app carries.
        </p>
      </header>

      <div className="btn-row">
        <Link className={buttonVariants({ variant: "default" })} href="/">
          Reference index
        </Link>
        <Link className={buttonVariants({ variant: "outline" })} href="/#contents">
          Contents
        </Link>
      </div>
    </main>
  );
}
