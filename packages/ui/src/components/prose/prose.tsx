import type { ReactNode } from "react";

/**
 * Prose atoms — the shared grammar for the long-form company / legal pages
 * (`/about`, `/team`, `/security`, `/quality`, `/services`, `/legal/*`).
 * Promoted verbatim from `apps/digithings-web/app/_company/prose.tsx` (D1,
 * #4429) so the shape is authored once and assembled by every site instead of
 * living app-locally.
 *
 * **Utilities only.** These emit no site/app CSS class — the reference canon
 * imports neither `@digithings/design/site/site.css` nor an app sheet — so the
 * exact values of the legacy `.section` / `.wrap` / `.kicker` / `.hero-title`
 * grammar are reproduced with token-backed utilities (source: `site.css`):
 *
 *   .section     `padding: clamp(4rem,9vw,7.5rem) 0` → `pt-[clamp(4rem,9vw,7.5rem)]`
 *                 (the old call site added `pb-0`, so only the top half survives)
 *   .wrap        → `w-full max-w-[var(--wrap)] mx-auto px-[var(--gutter)] relative z-[1]`
 *   .kicker      → `font-mono text-[0.8rem] tracking-[0.02em] text-accent`
 *   .hero-title  → `font-display font-normal text-[clamp(2.8rem,6.4vw,5rem)]
 *                   leading-[1.02] tracking-[-0.02em] mt-[1.4rem] mb-[1.2rem]
 *                   max-w-[16ch] [&_em]:italic [&_em]:text-accent`
 *
 * Server components — no hooks, no state. The consuming app still needs a
 * Tailwind `@source` line for this directory because the parts carry
 * utilities (Tailwind does not scan package sources on its own).
 */

export type MonoProps = { children: ReactNode };

/** Inline code. The site reset styles no bare `code` element, so the mono face
 *  has to be asked for explicitly; `0.92em` keeps the mono x-height in line
 *  with the surrounding body copy. */
export function Mono({ children }: MonoProps) {
  return <code className="font-mono text-[0.92em] text-ink">{children}</code>;
}

export type PageHeadProps = {
  /** The `//` mono eyebrow above the title. */
  kicker: string;
  /** The page title; `<em>` renders italic + accent. */
  title: ReactNode;
  /** The lede paragraph under the title. */
  children: ReactNode;
};

/** The standing long-form page opener: `//` kicker, display title, one lede
 *  paragraph. Mirrors the landing hero's shape at subpage scale. */
export function PageHead({ kicker, title, children }: PageHeadProps) {
  return (
    <section className="pt-[clamp(4rem,9vw,7.5rem)]">
      <div className="relative z-[1] mx-auto w-full max-w-[var(--wrap)] px-[var(--gutter)]">
        <span className="font-mono text-[0.8rem] tracking-[0.02em] text-accent">{kicker}</span>
        <h1 className="mt-[1.4rem] mb-[1.2rem] max-w-[16ch] font-display text-[clamp(2.8rem,6.4vw,5rem)] font-normal leading-[1.02] tracking-[-0.02em] [&_em]:italic [&_em]:text-accent">
          {title}
        </h1>
        <p className="max-w-[64ch] text-[1.08rem] leading-[1.7] text-ink-soft">{children}</p>
      </div>
    </section>
  );
}

export type RuledRowProps = {
  /** The mono lead cell — a file, env var, rule or term the body describes. */
  term: ReactNode;
  children: ReactNode;
};

/** A hairline-ruled definition row — the shape used for control lists,
 *  compatibility lists, residual-risk lists and gate lists. `term` is mono
 *  (it names a file, an env var or a rule); the body is sans. */
export function RuledRow({ term, children }: RuledRowProps) {
  return (
    <li className="grid gap-[0.35rem] border-t border-hair py-[1rem] last:border-b sm:grid-cols-[15rem_1fr] sm:gap-[1.5rem]">
      <span className="font-mono text-[0.86rem] leading-[1.5] text-ink">{term}</span>
      <span className="text-[0.9rem] leading-[1.65] text-ink-soft">{children}</span>
    </li>
  );
}

export type RuledListProps = { children: ReactNode };

/** The list wrapper for `RuledRow` — resets the marker and collapses the gap
 *  so the hairlines butt against each other. */
export function RuledList({ children }: RuledListProps) {
  return <ul className="m-0 grid list-none gap-0 p-0">{children}</ul>;
}
