"use client";

import { NavShell, type NavItem } from "@digithings/web";

// Two groups, deliberately: the frame's claim is that opening one closes the
// other, and a single group cannot show it.
const ITEMS: NavItem[] = [
  {
    label: "Docs",
    items: [
      { label: "Overview", href: "#" },
      { label: "Quickstart", href: "#" },
      { label: "API", href: "#" },
    ],
  },
  { label: "Architecture", href: "#" },
  { label: "Services", href: "#" },
  {
    label: "Company",
    items: [
      { label: "About", href: "#" },
      { label: "Team", href: "#" },
      { label: "Security", href: "#" },
      { label: "Quality", href: "#" },
    ],
  },
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
      links={ITEMS}
      homeLabel="digithings home"
      // This page frames three bars; each names its own landmark so they stay
      // distinguishable to a screen reader's landmark list.
      navLabel="Nav menu specimen"
    />
  );
}

/**
 * Nav menu — a dropdown group inside the production <NavShell/> bar. A `links`
 * entry that carries `items` instead of an `href` becomes a small index of
 * document pages: `button[aria-haspopup=menu]` + `div[role=menu]` +
 * `a[role=menuitem]`, one group open at a time. The panel opens on click and
 * on Enter/Space/ArrowDown from the trigger, moves with the arrow keys plus
 * Home/End, chooses with Enter or Space, and closes on Escape (focus returns to
 * the trigger), on Tab out (focus carries on from the trigger), on an outside
 * press, and on choosing an item. Items are `tabindex="-1"` — the trigger is
 * the menu's single tab stop — so a closed panel can ship its whole index in
 * the server-rendered HTML without parking a tab trap on the page. This frame
 * is live: click "Company", then "Docs", to watch the first close. Below 880px
 * there is no disclosure at all — the sheet behind the hamburger is already a
 * vertical index, so a group arrives there as a labelled section of links.
 */
export function NavMenuReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// nav menu"}</p>
      <h2 className="title">A menu is an index, not a gesture.</h2>
      <p className="section-copy">
        A <code>NavGroup</code> (<code>{"{ label, items }"}</code>) in <code>NavShell</code>&apos;s{" "}
        <code>links</code> array opens a short index of document pages under the bar — the pattern
        the top-level routes outgrew once About, Team, Security and Quality all wanted a place. The
        panel wears the settled bar&apos;s idiom (hairline, blurred band, no shadow) at the
        menu-open bar&apos;s density, and hangs off the bar&apos;s bottom edge, never inside it.
        Keyboard grammar is the menu-button pattern&apos;s core — Enter/Space, arrows, Home/End,
        Escape, Tab out, outside press — everything but the APG&apos;s character typeahead. Reduced
        motion keeps every state and drops the travel.
      </p>

      <p className="mt-[1.4rem] mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
        live — click Company or Docs, or tab to one and press ArrowDown / Escape
      </p>
      <div className="nsr-frame nsr-frame--settled nmr-frame">
        <DemoNav />
        <div
          className="flex flex-col gap-[0.7rem] px-[var(--gutter,1.5rem)] pt-[4.4rem] text-[0.86rem] text-ink-soft"
          aria-hidden="true"
        >
          <p className="m-0">Page copy runs under the panel — it dims nothing and locks nothing.</p>
          <p className="m-0">Opening a second group closes the first: one menu at a time.</p>
          <p className="m-0">An open menu also pins the bar, so scrolling can&apos;t carry it off.</p>
        </div>
      </div>
    </section>
  );
}
