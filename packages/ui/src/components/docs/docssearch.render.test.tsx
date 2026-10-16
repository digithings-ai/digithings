import { describe, expect, test } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import type { DocsNavItem } from "./DocsLayout";
import { DocsSearch, filterDocsItems } from "./DocsSearch";

const ITEMS: DocsNavItem[] = [
  { id: "self-host", label: "Self-host from GHCR" },
  { id: "authentication", label: "Authentication" },
  { id: "conventions", label: "Conventions" },
];

describe("filterDocsItems", () => {
  test("matches on the label, case-insensitively", () => {
    expect(filterDocsItems(ITEMS, "auth").map((i) => i.id)).toEqual(["authentication"]);
    expect(filterDocsItems(ITEMS, "SELF").map((i) => i.id)).toEqual(["self-host"]);
  });

  test("falls back to the id when the label is not a string", () => {
    const items: DocsNavItem[] = [{ id: "api-reference", label: <span>API</span> }];
    expect(filterDocsItems(items, "reference").map((i) => i.id)).toEqual(["api-reference"]);
    expect(filterDocsItems(items, "span")).toEqual([]);
  });

  test("an empty or whitespace query matches nothing", () => {
    expect(filterDocsItems(ITEMS, "")).toEqual([]);
    expect(filterDocsItems(ITEMS, "   ")).toEqual([]);
  });
});

describe("DocsSearch", () => {
  test("renders the search field with the ⌘K affordance and no result panel", () => {
    const html = renderToStaticMarkup(<DocsSearch items={ITEMS} />);
    expect(html).toContain('data-slot="search-bar"');
    expect(html).toContain("<kbd");
    expect(html).toContain("⌘K");
    expect(html).not.toContain("no section matches");
    expect(html).not.toContain('href="#self-host"');
  });

  test("carries the accessible name onto the input", () => {
    const html = renderToStaticMarkup(<DocsSearch items={ITEMS} label="Find a section" />);
    expect(html).toContain('aria-label="Find a section"');
    expect(html).toContain('type="search"');
  });

  test("emits no palette utility", () => {
    const html = renderToStaticMarkup(<DocsSearch items={ITEMS} />);
    expect(html).not.toMatch(/text-(emerald|sky|amber|rose|violet|fuchsia|blue|green|red)-/);
  });
});
