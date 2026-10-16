/**
 * Page TOC — a lightweight "on this page" anchor list for long reference
 * pages built from many stacked sections. Plain links to existing #ids on
 * the page; no scroll-spy, no sticky rail, no new visual language — the
 * link treatment mirrors .site-nav-links a exactly (mono, ink-mute, ink on
 * hover) so it reads as more site chrome, not a new widget. Reusable across
 * any reference page; not finance-specific — a page just supplies its own
 * section ids and labels.
 */
export type PageTocItem = { id: string; label: string };

export function PageToc({ items }: { items: PageTocItem[] }) {
  return (
    <nav aria-label="On this page" className="mt-[1.4rem]">
      <p className="kicker">{"// on this page"}</p>
      <ul className="m-0 mt-[0.6rem] flex list-none flex-wrap gap-x-[1rem] gap-y-[0.4rem] p-0">
        {items.map((item) => (
          <li key={item.id}>
            <a
              href={`#${item.id}`}
              className="font-mono text-[0.72rem] tracking-[0.04em] text-ink-mute no-underline transition-colors duration-200 hover:text-ink"
            >
              {item.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
