"use client";

import { NavShell, type NavItem } from "@digithings/web";

const ITEMS: NavItem[] = [
  { label: "Docs", href: "#" },
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
    />
  );
}

/**
 * Nav menu — a dropdown group inside the production <NavShell/> bar. A `links`
 * entry that carries `items` instead of an `href` becomes a small index of
 * document pages: `button[aria-haspopup=menu]` + `div[role=menu]` +
 * `a[role=menuitem]`, one group open at a time. The panel opens on click and
 * on Enter/Space/ArrowDown from the trigger, moves with the arrow keys plus
 * Home/End, activates on Enter or Space, and closes on Escape (focus returns to
 * the trigger), on an outside press, on choosing an item, and when focus leaves
 * the group by any route. Items are `tabindex="-1"` — the trigger is the menu's
 * single tab stop — so a closed panel can ship its whole index to the server
 * without parking a tab trap on the page. Two deliberate omissions: no
 * first-character type-ahead (four items don't need it), and the bar is a nav
 * of links rather than a `role="menubar"`, so ArrowLeft/ArrowRight do not walk
 * between top-level items. This frame is live: click "Company" (or tab to it
 * and press ArrowDown). Below 880px there is no disclosure at all — the sheet
 * behind the hamburger is already a vertical index, so a group arrives there as
 * a labelled section of links.
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
        panel wears the settled bar&apos;s own dress (hairline, blurred band, no shadow) and hangs
        off the bar&apos;s bottom edge, never inside it. The keyboard grammar is the WAI-ARIA menu
        button&apos;s, less type-ahead: open on Enter, Space or ArrowDown, walk with the arrows and
        Home/End, activate on Enter or Space, dismiss on Escape or on tabbing out. Reduced motion
        keeps every state and drops the travel.
      </p>

      <p className="mt-[1.4rem] mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
        live — click Company, or tab to it and press ArrowDown / Escape
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
