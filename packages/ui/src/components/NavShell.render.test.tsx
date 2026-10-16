/**
 * SSR smoke tests for <NavShell/>'s dropdown groups: the wide bar's trigger
 * carries the menu-button ARIA contract, the panel ships its full index of
 * menuitems on the server (so the links are crawlable and the panel can
 * transition rather than mount), and nothing is open by default.
 *
 * The strip is the only surface asserted here: the narrow sheet lives behind a
 * portal + mount gate, so it renders to nothing on the server by design.
 * `showThemeToggle={false}` keeps ThemeProvider (and its context) out of it.
 */
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
});
