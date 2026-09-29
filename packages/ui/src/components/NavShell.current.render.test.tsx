/**
 * SSR tests for NavShell's current-route marking. `currentPath` is the whole
 * contract: a site passes its pathname and NavShell decides once which link
 * wears `aria-current="page"` — an exact real-route match only. External links
 * and same-page anchors (`/#pipeline`) never qualify (several anchors share one
 * pathname, so marking them would light up the whole row), and a missing
 * `currentPath` marks nothing.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { NavShell } from "./NavShell";
import { hrefIsCurrent, type NavItem } from "./chrome";

const LINKS: NavItem[] = [
  { label: "Docs", href: "/docs" },
  { label: "Changelog", href: "/changelog" },
  { label: "Pipeline", href: "/#pipeline" },
  { label: "Company", items: [{ label: "Team", href: "/team" }] },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
];

const render = (currentPath?: string) =>
  renderToStaticMarkup(
    <NavShell
      brand="digithings"
      links={LINKS}
      currentPath={currentPath}
      showThemeToggle={false}
    />,
  );

describe("NavShell aria-current", () => {
  it("marks exactly the link matching currentPath", () => {
    const html = render("/docs");
    expect(html.match(/aria-current="page"/g)).toHaveLength(1);
    expect(html).toMatch(/href="\/docs"[^>]*aria-current="page"/);
  });

  it("does not mark a different route", () => {
    const html = render("/docs");
    expect(html).not.toMatch(/href="\/changelog"[^>]*aria-current/);
  });

  it("never marks a same-page anchor", () => {
    const html = render("/");
    expect(html).not.toMatch(/href="\/#pipeline"[^>]*aria-current/);
  });

  it("never marks an external link", () => {
    const html = render("/docs");
    expect(html).not.toMatch(/href="https:\/\/digiquant\.io"[^>]*aria-current/);
  });

  it("marks a dropdown menu item that matches", () => {
    const html = render("/team");
    expect(html.match(/aria-current="page"/g)).toHaveLength(1);
    expect(html).toMatch(/href="\/team"[^>]*aria-current="page"/);
  });

  it("marks nothing when currentPath is omitted", () => {
    expect(render()).not.toContain("aria-current");
  });

  it("treats a trailing slash as the same route", () => {
    expect(render("/docs/")).toMatch(/href="\/docs"[^>]*aria-current="page"/);
  });
});

describe("hrefIsCurrent", () => {
  it("matches exact routes and their trailing-slash shape", () => {
    expect(hrefIsCurrent("/docs", "/docs")).toBe(true);
    expect(hrefIsCurrent("/docs", "/docs/")).toBe(true);
    expect(hrefIsCurrent("/docs/", "/docs")).toBe(true);
    expect(hrefIsCurrent("/docs", "/docs/api")).toBe(false);
  });

  it("rejects external and anchored hrefs", () => {
    expect(hrefIsCurrent("https://digiquant.io", "https://digiquant.io")).toBe(false);
    expect(hrefIsCurrent("/#pipeline", "/")).toBe(false);
    expect(hrefIsCurrent("#section", "/")).toBe(false);
  });

  it("returns false with no pathname", () => {
    expect(hrefIsCurrent("/docs", undefined)).toBe(false);
  });
});
