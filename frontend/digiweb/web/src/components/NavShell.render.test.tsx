/**
 * SSR smoke tests for <NavShell/>'s dropdown groups: the wide bar's trigger
 * carries the menu-button ARIA contract, the panel ships its full index of
 * menuitems in the server-rendered HTML (so the links are crawlable and the
 * panel can transition rather than mount), and nothing is open by default.
 *
 * The strip is the only surface asserted here: the narrow sheet lives behind a
 * portal + mount gate, so it renders to nothing on the server by design.
 * `showThemeToggle={false}` keeps ThemeProvider (and its context) out of it.
 *
 * The keyboard grammar itself is covered by nav-menu-core.test.ts (the pure
 * key→intent map) — this package has no DOM harness, so the last block below
 * guards the one styling contract that grammar silently depends on.
 */
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { NavShell } from "./NavShell";
import type { NavItem } from "./chrome";

const ITEMS: NavItem[] = [
  { label: "Docs", href: "/docs" },
  {
    label: "Company",
    items: [
      { label: "About", href: "/about" },
      { label: "Team", href: "/team" },
      { label: "Security", href: "/security" },
    ],
  },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
];

const render = (items: NavItem[] = ITEMS) =>
  renderToStaticMarkup(<NavShell brand="digithings" links={items} showThemeToggle={false} />);

describe("NavShell groups", () => {
  it("wires the trigger as a menu button", () => {
    const html = render();
    expect(html).toContain('aria-haspopup="menu"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain("nav-shell-group-trigger");
    expect(html).toContain("Company");
  });

  it("renders the group's items as menuitems inside a menu", () => {
    const html = render();
    expect(html).toContain('role="menu"');
    expect(html).toContain('aria-label="Company"');
    expect(html.match(/role="menuitem"/g)).toHaveLength(3);
    for (const label of ["About", "Team", "Security"]) expect(html).toContain(label);
    // roving focus: the trigger is the menu's only tab stop
    expect(html).toContain('tabindex="-1"');
  });

  it("opens nothing by default", () => {
    const html = render();
    // the panel is parked: class carries no .is-open, and it is hidden from AT
    expect(html).toContain('class="nav-shell-menu"');
    expect(html).toMatch(/role="menu"[^>]*aria-hidden="true"/);
    expect(html).toContain('data-open="false"'); // the group box
    expect(html).toContain('data-group-open="false"'); // and the bar it sits in
  });

  it("still renders a flat NavLink[] with no group machinery", () => {
    const html = render([
      { label: "Docs", href: "/docs" },
      { label: "Contact", href: "/#contact" },
    ]);
    expect(html).toContain('href="/docs"');
    expect(html).not.toContain('role="menu"');
    expect(html).not.toContain("aria-haspopup");
  });

  it("keeps external links safe and marked in both a group and the strip", () => {
    const html = render([
      { label: "Company", items: [{ label: "Blog", href: "https://example.com", external: true }] },
    ]);
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("names the wayfinding landmark Primary, and lets a page rename it", () => {
    // A page that frames more than one bar (the design reference) needs
    // distinguishable landmarks; every product site keeps the default.
    expect(render()).toContain('aria-label="Primary"');
    const specimen = renderToStaticMarkup(
      <NavShell brand="digithings" links={ITEMS} showThemeToggle={false} navLabel="Bar specimen" />,
    );
    expect(specimen).toContain('aria-label="Bar specimen"');
    expect(specimen).not.toContain('aria-label="Primary"');
  });
});

/* The panel's dress is load-bearing for its keyboard grammar, and this package
   has no DOM harness to catch a regression in it — so the contract is asserted
   against the stylesheet text itself (read from disk: vitest stubs CSS imports,
   `?raw` included — see src/node-fs.d.ts). */
const CSS = readFileSync(new URL("../styles/nav-shell.css", import.meta.url), "utf8");

/** Body of the top-level rule whose selector list is exactly `selector`. The
 *  leading newline anchors it to column 0, so the indented restatements inside
 *  the reduced-motion media query can't match. */
function ruleBody(selector: string): string {
  const at = CSS.indexOf(`\n${selector} {`);
  if (at < 0) throw new Error(`nav-shell.css has no top-level \`${selector}\` rule`);
  const open = CSS.indexOf("{", at);
  const close = CSS.indexOf("}", open);
  return CSS.slice(open + 1, close);
}

/** The rule's `transition` value, comments stripped. */
function transitionOf(selector: string): string {
  const body = ruleBody(selector).replace(/\/\*[\s\S]*?\*\//g, "");
  const match = /transition:([^;]*);/.exec(body);
  if (!match) throw new Error(`\`${selector}\` declares no transition`);
  return match[1];
}

describe("dropdown panel visibility contract", () => {
  it("steps visibility on close and flips it instantly on open", () => {
    // Opening a group focuses an item, and focus() on a `visibility: hidden`
    // element is a silent no-op — so the open state must not interpolate
    // visibility (a transitioned `visibility` still computes as `hidden` at
    // t=0), while the closed state has to wait out the fade before hiding.
    // A restyle that folds `visibility` back into the open transition would
    // make the keyboard grammar look dead; this is the guard for it.
    expect(transitionOf(".nav-shell-menu")).toContain("visibility 0s");
    expect(transitionOf(".nav-shell-menu.is-open")).not.toContain("visibility");
    expect(ruleBody(".nav-shell-menu.is-open")).toContain("visibility: visible");
  });

  it("keeps the open panel out of the bar's yield", () => {
    // The pinned-bar rule the scroll listener cooperates with: without it, a
    // scroll-down would carry an open panel off the top of the page.
    expect(CSS).toContain('.nav-shell[data-group-open="true"].is-hidden');
  });
});
