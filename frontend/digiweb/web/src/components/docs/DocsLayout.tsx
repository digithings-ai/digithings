"use client";
import { useEffect, useState, type ReactNode } from "react";

/**
 * Docs shell: a sticky, scroll-spied sidebar on desktop and a native
 * <details> disclosure on mobile — the sidebar never just vanishes
 * (canon §17). One nav model, rendered twice. Presentation-generic: nav
 * groups, hero, and content arrive as props/children; nothing app-specific
 * is baked in. Structural CSS (grid reveal, sticky offset, disclosure
 * marker, scroll margins) lives in styles/docs.css; consumers with fixed
 * chrome set --docs-nav-h on the shell or an ancestor.
 */

export interface DocsNavItem {
  /** id of the section element this entry links to (`#id`) and scroll-spies. */
  id: string;
  label: ReactNode;
}

export interface DocsNavGroup {
  label: ReactNode;
  items: DocsNavItem[];
}

export interface DocsHero {
  kicker?: ReactNode;
  title: ReactNode;
  lede?: ReactNode;
  actions?: ReactNode;
}

export function DocsLayout({
  nav,
  hero,
  children,
  contentsLabel = "contents",
  ariaLabel = "docs",
}: {
  nav: DocsNavGroup[];
  hero?: DocsHero;
  children: ReactNode;
  /** Label on the collapsed mobile disclosure. */
  contentsLabel?: string;
  /** aria-label shared by both renderings of the nav. */
  ariaLabel?: string;
}) {
  const [active, setActive] = useState(nav[0]?.items[0]?.id ?? "");

  // Scroll-spy over every nav-item id. Keyed on the joined id list, not the
  // nav array identity, so inline props don't re-subscribe every render.
  const idsKey = nav.map((g) => g.items.map((i) => i.id).join("\n")).join("\n");
  useEffect(() => {
    const els = idsKey
      .split("\n")
      .map((id) => document.getElementById(id))
      .filter((e): e is HTMLElement => !!e);
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-20% 0px -70% 0px", threshold: 0 },
    );
    els.forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, [idsKey]);

  const sideNav = (
    <nav aria-label={ariaLabel} className="flex flex-col gap-[0.1rem]">
      {nav.map((g, gi) => (
        <div key={gi} className="mt-[0.8rem] flex flex-col gap-[0.1rem]">
          <span className="mb-[0.2rem] px-[0.6rem] font-mono text-[0.68rem] uppercase tracking-[0.12em] text-ink-mute">
            {g.label}
          </span>
          {g.items.map((it) => (
            <a
              key={it.id}
              href={`#${it.id}`}
              aria-current={active === it.id ? "true" : undefined}
              className={`rounded-[7px] border-l-2 px-[0.6rem] py-[0.28rem] font-mono text-[0.82rem] no-underline transition-colors duration-150 ease-brand ${
                active === it.id
                  ? "border-l-accent bg-accent-weak text-ink"
                  : "border-l-transparent text-ink-soft hover:bg-accent-weak hover:text-ink"
              }`}
            >
              {it.label}
            </a>
          ))}
        </div>
      ))}
    </nav>
  );

  return (
    <div className="docs-shell">
      <aside className="docs-side">{sideNav}</aside>

      <div className="docs-content flex min-w-0 flex-col gap-[clamp(1.6rem,3.5vw,2.6rem)]">
        <details className="docs-side-mobile mb-[1.3rem] rounded-[10px] border border-hair px-[0.85rem] py-[0.55rem]">
          <summary className="cursor-pointer font-mono text-[0.7rem] uppercase tracking-[0.12em] text-ink-mute">
            {contentsLabel}
          </summary>
          {sideNav}
        </details>

        {hero && (
          <header className="docs-hero">
            {hero.kicker != null && (
              <p className="m-0 font-mono text-[0.68rem] uppercase tracking-[0.14em] text-accent">
                {hero.kicker}
              </p>
            )}
            <h1 className="mb-[0.7rem] mt-[0.5rem] font-display text-[clamp(1.9rem,4vw,2.7rem)] font-normal tracking-[-0.02em] text-ink">
              {hero.title}
            </h1>
            {hero.lede != null && (
              <p className="m-0 max-w-[60ch] leading-[1.6] text-ink-soft">{hero.lede}</p>
            )}
            {hero.actions != null && <div className="mt-[1rem]">{hero.actions}</div>}
          </header>
        )}

        {children}
      </div>
    </div>
  );
}
