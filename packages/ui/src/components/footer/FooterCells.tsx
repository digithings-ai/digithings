/**
 * The footer as a hairline table, not a link cloud (D1, #4429). Every top-level
 * destination gets one cell of equal weight, separated by the same 1px hairline
 * the rest of the site is drawn with, and the legal strip sits underneath.
 * This is the opencode.ai footer: one closed rectangle of centred cells, no
 * column headings, no nested groups, no background change. The legal line
 * (copyright, privacy, sibling site, profiles) sits outside the rectangle.
 * The row is two cells wide until the viewport can hold five across.
 */

import type { ReactNode } from "react";

export interface FooterCell {
  /** Sentence-case destination name. */
  label: string;
  href: string;
  external?: boolean;
  /** Optional muted footnote beside the label, e.g. a release tag or a count. */
  note?: string;
}

export interface FooterMetaLink {
  label: string;
  href: string;
  external?: boolean;
}

export interface FooterCellsProps {
  cells: FooterCell[];
  /** One line of meta, e.g. "© 2026 digithings · open core". */
  meta?: string;
  /** Legal-strip links rendered after the meta line. */
  metaLinks?: FooterMetaLink[];
  /** Quiet profile row (typically <SocialRow/>) on the legal strip. */
  profiles?: ReactNode;
  /** How many equal cells sit on one row once the viewport is wide enough. */
  columns?: 3 | 4 | 5;
  /** Block between the boxes and the legal strip — the columnar sitemap. */
  below?: ReactNode;
  className?: string;
}

const NAV_CLASS = {
  3: "grid grid-cols-1 border-t border-l border-hair sm:grid-cols-3",
  4: "grid grid-cols-2 border-t border-l border-hair sm:grid-cols-4",
  5: "grid grid-cols-2 border-t border-l border-hair lg:grid-cols-5",
} as const;

const CELL =
  "flex min-h-[4.5rem] items-center justify-center gap-[0.55rem] border-r border-b border-hair px-[0.75rem] py-[1.15rem] text-center font-mono text-[1rem] leading-[1.4] text-ink no-underline transition-colors duration-150 ease-brand hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:ring-[3px] focus-visible:ring-accent/30 focus-visible:outline-none lg:min-h-[5.5rem]";

export function FooterCells({
  cells,
  meta,
  metaLinks,
  profiles,
  columns = 5,
  below,
  className,
}: FooterCellsProps) {
  const legal = Boolean(meta || metaLinks?.length || profiles);
  return (
    <footer
      className={[
        "mx-auto w-full max-w-[calc(var(--frame-w)+2*var(--page-pad))]",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <nav aria-label="Footer" className={NAV_CLASS[columns]}>
        {cells.map((cell) => (
          <a
            key={cell.href + cell.label}
            href={cell.href}
            target={cell.external ? "_blank" : undefined}
            rel={cell.external ? "noopener noreferrer" : undefined}
            className={CELL}
          >
            <span>{cell.label}</span>
            {cell.note ? (
              <span className="text-[var(--type-meta)] tracking-[0.02em] text-ink-mute">
                [{cell.note}]
              </span>
            ) : null}
          </a>
        ))}
      </nav>
      {below}
      {legal ? (
        <div className="footer-legal flex flex-wrap items-center justify-center gap-x-[1.25rem] gap-y-[0.75rem] px-[var(--page-pad)] py-[1.35rem] font-mono text-[var(--type-meta)] tracking-[0.02em] text-ink-mute">
          {meta ? <span>{meta}</span> : null}
          {metaLinks?.map((link) => (
            <a
              key={link.href}
              href={link.href}
              target={link.external ? "_blank" : undefined}
              rel={link.external ? "noopener noreferrer" : undefined}
              className="underline-offset-[3px] hover:text-ink hover:underline"
            >
              {link.label}
            </a>
          ))}
          {profiles}
        </div>
      ) : null}
    </footer>
  );
}
