/** Shared prose atoms for the company pages (/about, /team, /security,
 *  /quality, /services, /legal/*, /brand).
 *
 *  These are composition helpers, not a new UI family: every one of them emits
 *  existing canon classes (.kicker, .hero-title, .section, .wrap) plus
 *  token-backed Tailwind utilities. No CSS is added anywhere — the frontend
 *  canon guard ratchets on new column-0 class families in app CSS, and pages
 *  are supposed to assemble from shared primitives, so anything with real dress
 *  belongs in @digithings/web, not here.
 *
 *  `_company` is underscore-prefixed: App Router private folders are opted out
 *  of routing, so this file is not a route.
 *
 *  Server components — no hooks, no state.
 */
import type { ReactNode } from "react";

/** Inline code. The site's reset styles no bare `code` element, so the mono
 *  face has to be asked for explicitly; `0.92em` keeps mono x-height in line
 *  with the surrounding sans body copy. */
export function Mono({ children }: { children: ReactNode }) {
  return <code className="font-mono text-[0.92em] text-ink">{children}</code>;
}

/** The standing page opener: `//` kicker, mono .hero-title, one lede
 *  paragraph. Mirrors the landing hero's shape at subpage scale (site.css
 *  documents .hero-title as the standalone detail-page title). `pb-0` on the
 *  section lets the first content section own the gap. */
export function PageHead({
  kicker,
  title,
  children,
}: {
  kicker: string;
  title: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="section pb-0">
      <div className="wrap">
        <span className="kicker">{kicker}</span>
        <h1 className="hero-title">{title}</h1>
        <p className="max-w-[64ch] text-[1.08rem] leading-[1.7] text-ink-soft">{children}</p>
      </div>
    </section>
  );
}

/** A hairline-ruled definition row — the shape used for control lists,
 *  residual-risk lists and gate lists. `term` is mono (it names a file, an
 *  env var or a rule); the body is sans. */
export function RuledRow({ term, children }: { term: ReactNode; children: ReactNode }) {
  return (
    <li className="grid gap-[0.35rem] border-t border-hair py-[1rem] last:border-b sm:grid-cols-[15rem_1fr] sm:gap-[1.5rem]">
      <span className="font-mono text-[0.86rem] leading-[1.5] text-ink">{term}</span>
      <span className="text-[0.9rem] leading-[1.65] text-ink-soft">{children}</span>
    </li>
  );
}

/** The list wrapper for RuledRow — resets the marker and collapses the gap so
 *  the hairlines butt against each other. */
export function RuledList({ children }: { children: ReactNode }) {
  return <ul className="m-0 grid list-none gap-0 p-0">{children}</ul>;
}
