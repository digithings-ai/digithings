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
    expect(PAGED_CSS).toContain(".book-chapter { break-before: page; }");
    expect(PAGED_CSS).toContain("[role=\"status\"]");
    expect(PRINT_CSS).toContain(".running-element");
    expect(PRINT_CSS).toContain(".book-toc__ref");
  });
});
