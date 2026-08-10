"use client";

import { NavShell, GitHubGlyph, type NavLink } from "@digithings/web";

const LINKS: NavLink[] = [
  { label: "Product", href: "#" },
  { label: "Pricing", href: "#" },
  { label: "Docs", href: "#" },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
];

function DemoNav() {
  return (
    <NavShell
      brand={
        <span className="font-mono text-[0.82rem] font-medium">
          digi<em className="not-italic text-accent">things</em>
        </span>
      }
      links={LINKS}
      homeLabel="digithings home"
      actions={
        <a
          className="btn-icon"
          href="https://github.com/digithings-ai"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="digithings on GitHub"
        >
          <GitHubGlyph />
        </a>
      }
      cta={
        <a
          className="inline-flex items-center gap-[0.45rem] rounded-[999px] border border-hair bg-surface px-[0.95rem] py-[0.45rem] font-mono text-[0.78rem] text-ink"
          href="#"
        >
          Launch olympus <span aria-hidden="true">→</span>
        </a>
      }
    />
  );
}

/**
 * Nav shell — the production top-bar primitive from @digithings/web, framed as
 * a static specimen in its two dress states: at rest (transparent over the
 * hero) and settled (hairline + blurred band once the page has scrolled).
 * One component owns the grammar both marketing sites used to copy-paste —
 * settle after 8px, yield past 180px on scroll-down and return on scroll-up,
 * a portal sheet behind the hamburger on narrow viewports — while brand,
 * links, tail actions and the sheet CTA arrive as props. The frames pin each
 * state so the bar stands still for inspection; the live scroll behavior is
 * the scroll-aware nav above.
 */
export function NavShellReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// nav shell"}</p>
      <h2 className="title">One bar, every site.</h2>
      <p className="section-copy">
        <code>NavShell</code> from <code>@digithings/web</code> supersedes the per-app nav copies:
        the scroll grammar, portal sheet, scroll lock and keyboard handling are owned once; brand,
        links, tail actions and the sheet CTA are props. In production the bar is viewport-fixed —
        these frames contain it and pin one dress each. On a narrow viewport the frames show the
        narrow dress, and the hamburger opens the real full-height portal sheet.
      </p>

      <p className="mt-[1.4rem] mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
        at rest — top of page, transparent over the hero
      </p>
      <div className="nsr-frame nsr-frame--rest">
        <DemoNav />
        <p
          className="m-0 px-[var(--gutter,1.5rem)] pt-[4.4rem] font-display text-[1.7rem] text-ink"
          aria-hidden="true"
        >
          The hero begins here.
        </p>
      </div>

      <p className="mt-[1.4rem] mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
        settled — after 8px of scroll: hairline + blurred band
      </p>
      <div className="nsr-frame nsr-frame--settled">
        <DemoNav />
        <div
          className="flex flex-col gap-[0.7rem] px-[var(--gutter,1.5rem)] pt-[1.1rem] text-[0.86rem] text-ink-soft"
          aria-hidden="true"
        >
          <p className="m-0">Body copy runs under the translucent band as the page scrolls.</p>
          <p className="m-0">The bar never shrinks and the mark never animates — it settles.</p>
          <p className="m-0">Scroll down past 180px and it yields; scroll up and it returns.</p>
        </div>
      </div>
    </section>
  );
}
