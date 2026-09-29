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
  /**
   * A page link instead of an in-page section: the entry is not spied and is
   * lit only when `current`. Lets one sidebar span a docs site's pages.
   */
  href?: string;
  current?: boolean;
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

/**
 * Scroll-spy: the last of `ids` whose element's top has passed a line a
 * quarter down the viewport. Position rather than intersection, so a section
 * taller than the viewport stays active the whole way through it.
 */
function useSpy(ids: string[], fallback: string): string {
  const [active, setActive] = useState(fallback);
  const key = ids.join("\n");
  useEffect(() => {
    const list = key ? key.split("\n") : [];
    let frame = 0;
    const read = () => {
      frame = 0;
      const line = window.innerHeight * 0.25;
      let next = list[0] ?? "";
      for (const id of list) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top <= line) next = id;
      }
      setActive(next);
    };
    const onScroll = () => {
      if (frame === 0) frame = requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [key]);
  return active;
}

export function DocsLayout({
  nav,
  hero,
  children,
  rail,
  railLabel = "on this page",
  search,
  contentsLabel = "contents",
  ariaLabel = "docs",
  className,
}: {
  nav: DocsNavGroup[];
  hero?: DocsHero;
  children: ReactNode;
  /**
   * On-this-page entries: a second, narrower rail on wide viewports. Either
   * one list for the whole page, or a list per nav entry (keyed by nav item
   * id) so the rail follows the section being read.
   */
  rail?: DocsNavItem[] | Record<string, DocsNavItem[]>;
  /** Heading above the on-this-page rail. */
  railLabel?: ReactNode;
  /** Search affordance, rendered above the hero. */
  search?: ReactNode;
  /** Label on the collapsed mobile disclosure. */
  contentsLabel?: string;
  /** aria-label shared by both renderings of the nav. */
  ariaLabel?: string;
  /** Extra classes on the shell (e.g. a wider max-width). */
  className?: string;
}) {
  // Two spies: the sidebar tracks its entries, the rail tracks its own, so a
  // lit sub-section never un-lights the entry it belongs to.
  const navIds = nav.flatMap((g) => g.items.filter((i) => i.href == null).map((i) => i.id));
  const navActive = useSpy(navIds, navIds[0] ?? "");
  const railItems = Array.isArray(rail) ? rail : rail?.[navActive];
  const railIds = (railItems ?? []).map((i) => i.id);
  const railActive = useSpy(railIds, railIds[0] ?? "");

  const itemLink = (it: DocsNavItem, active: string) => {
    const on = it.href != null ? it.current === true : active === it.id;
    const current = it.href != null ? "page" : "true";
    return (
      <a
        key={it.id}
        href={it.href ?? `#${it.id}`}
        aria-current={on ? current : undefined}
        className={`rounded-none border-s-2 px-[0.6rem] py-[0.28rem] font-mono text-[0.82rem] no-underline transition-colors duration-150 ease-brand ${
          on
            ? "border-s-accent bg-accent-weak text-ink"
            : "border-s-transparent text-ink-soft hover:bg-accent-weak hover:text-ink"
        }`}
      >
        {it.label}
      </a>
    );
  };

  const sideNav = (
    <nav aria-label={ariaLabel} className="flex flex-col gap-[0.1rem]">
      {nav.map((g, gi) => (
        <div key={gi} className="mt-[0.8rem] flex flex-col gap-[0.1rem]">
          <span className="mb-[0.2rem] px-[0.6rem] font-mono text-[0.68rem] uppercase tracking-[0.12em] text-ink-mute">
            {g.label}
          </span>
          {g.items.map((it) => itemLink(it, navActive))}
        </div>
      ))}
    </nav>
  );

  const railNav =
    railItems && railItems.length > 0 ? (
      <nav
        aria-label={typeof railLabel === "string" ? railLabel : "on this page"}
        className="flex flex-col gap-[0.1rem]"
      >
        <span className="mb-[0.2rem] px-[0.6rem] font-mono text-[0.68rem] uppercase tracking-[0.12em] text-ink-mute">
          {railLabel}
        </span>
        {railItems.map((it) => itemLink(it, railActive))}
      </nav>
    ) : null;

  return (
    <div className={className ? `docs-shell ${className}` : "docs-shell"}>
      <aside className="docs-side">{sideNav}</aside>

      <div className="docs-content flex min-w-0 flex-col gap-[clamp(1.6rem,3.5vw,2.6rem)]">
        <details className="docs-side-mobile mb-[1.3rem] rounded-none border border-hair px-[0.85rem] py-[0.55rem]">
          <summary className="cursor-pointer font-mono text-[0.7rem] uppercase tracking-[0.12em] text-ink-mute">
            {contentsLabel}
          </summary>
          {sideNav}
        </details>

        {search != null && <div className="docs-search">{search}</div>}

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

      {/* The column stays whenever a rail is given, so an entry with no
          sub-sections empties it instead of reflowing the page. */}
      {rail != null && <aside className="docs-rail">{railNav}</aside>}
    </div>
  );
}
