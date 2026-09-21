/**
 * The footer as a hairline table, not a link cloud (D1, #4429). Every top-level
 * destination gets one cell of equal weight, separated by the same 1px hairline
 * the rest of the site is drawn with, and the legal strip sits underneath. This
 * is the opencode.ai footer shape on digiweb tokens: no column headings, no
 * nested groups, no background change — five destinations and one line of meta.
 * Utilities only; the consuming app's frame supplies the inline inset.
 */

export interface FooterCell {
  /** Sentence-case destination name. */
  label: string;
  href: string;
  external?: boolean;
  /** Optional right-aligned mono footnote, e.g. a release tag or a count. */
  note?: string;
}

export interface FooterCellsProps {
  cells: FooterCell[];
  /** One line of meta, e.g. "© 2026 digithings · open core". */
  meta?: string;
  /** Legal-strip links rendered after the meta line. */
  metaLinks?: { label: string; href: string }[];
  className?: string;
}

const CELL =
  "flex items-baseline justify-between gap-[0.75rem] border-b border-hair px-[var(--page-pad)] py-[1.5rem] text-[length:var(--type-body)] leading-[1.5] text-ink no-underline transition-colors duration-150 ease-brand hover:bg-surface-2 lg:border-b-0 lg:border-l lg:first:border-l-0";

export function FooterCells({ cells, meta, metaLinks, className }: FooterCellsProps) {
  return (
    <footer className={["border-t border-hair", className].filter(Boolean).join(" ")}>
      <nav aria-label="Footer" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5">
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
              <span className="font-mono text-[var(--type-meta)] tracking-[0.02em] text-ink-mute">
                {cell.note}
              </span>
            ) : null}
          </a>
        ))}
      </nav>
      {meta || metaLinks?.length ? (
        <div className="flex flex-wrap items-baseline gap-x-[1.25rem] gap-y-[0.5rem] border-t border-hair px-[var(--page-pad)] py-[1.25rem] font-mono text-[var(--type-meta)] tracking-[0.02em] text-ink-mute">
          {meta ? <span>{meta}</span> : null}
          {metaLinks?.map((link) => (
            <a key={link.href} href={link.href} className="underline-offset-[3px] hover:text-ink hover:underline">
              {link.label}
            </a>
          ))}
        </div>
      ) : null}
    </footer>
  );
}
