import { describe, expect, it } from "vitest";

import { PAGED_CSS, PRINT_CSS } from "./printCss";

/**
 * Both stylesheets are template literals, and a backtick inside one closes it.
 * The remainder of the file is then parsed as TypeScript, which surfaces as a
 * nonsense error three hundred characters away from the cause — twice on this
 * file. These two assertions turn that into a failing test at the line.
 */
describe("the stylesheets are well-formed template literals", () => {
  it.each([
    ["PRINT_CSS", PRINT_CSS],
    ["PAGED_CSS", PAGED_CSS],
  ])("%s contains no stray backtick or interpolation", (_name, css) => {
    expect(css).not.toContain("`");
    expect(css).not.toContain("${");
  });

  it.each([
    ["PRINT_CSS", PRINT_CSS],
    ["PAGED_CSS", PAGED_CSS],
  ])("%s is CSS, not a fragment of TypeScript", (_name, css) => {
    const braces = (css.match(/\{/g) ?? []).length;
    const closes = (css.match(/\}/g) ?? []).length;
    expect(braces).toBe(closes);
    // A healthy stylesheet is long. A template literal that closed early leaves
    // a short remainder, which is the shape of this bug.
    expect(css.length).toBeGreaterThan(400);
  });

  it("every colour in the printed sheets is a token reference", () => {
    // The canon guard exempts only lines carrying a token; a literal here would
    // print a colour the rest of the site cannot change.
    const literals = [...`${PRINT_CSS}\n${PAGED_CSS}`.matchAll(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/g)];
    expect(literals.map((m) => m[0])).toEqual([]);
  });

  it("declares the page box and the chrome rules the print step relies on", () => {
    expect(PAGED_CSS).toContain("@page");
    expect(PAGED_CSS).toContain(".book-chapter { break-before: page; margin-top: 0; }");
    expect(PAGED_CSS).toContain(".book-colophon");
    expect(PAGED_CSS).toContain("[role=\"status\"]");
    expect(PAGED_CSS).toContain(".book-cover");
    expect(PAGED_CSS).toContain(".book-contents");
    expect(PAGED_CSS).toContain(".book-toc__leader");
    expect(PRINT_CSS).toContain(".running-element");
    expect(PRINT_CSS).toContain(".book-toc__ref");
  });
});

describe("an empty wrapper clone cannot claim a column", () => {
  it("pins the height of the html/body clones the engine copies into a page box", () => {
    // The site gives body a height of 100%. In print that resolves against the
    // page's content box, so an empty clone measured a full page tall, took a
    // whole column of the page flow, and pushed the cover off the first sheet.
    expect(PAGED_CSS).toContain(".pagedjs_page html, .pagedjs_page body {");
    expect(PAGED_CSS).toContain(".pagedjs_page html, .pagedjs_page body {\n  height: auto !important;");
  });
});

describe("diagrams print once", () => {
  it("hides the other theme's render with a selector that outranks the viewport img rule", () => {
    // '.book-figure__viewport img' sets display: block !important; a bare
    // '.book-figure__dark' loses to it and the dark render printed under the
    // light one on every diagram page.
    expect(PAGED_CSS).toContain(".book-figure__viewport img.book-figure__dark { display: none !important; }");
    expect(PAGED_CSS).toContain(
      ':root[data-theme="dark"] .book-figure__viewport img.book-figure__light { display: none !important; }',
    );
  });
});
