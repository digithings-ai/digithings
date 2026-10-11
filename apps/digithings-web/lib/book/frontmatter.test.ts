import { describe, expect, it } from "vitest";

import {
  FrontmatterError,
  hasFrontmatter,
  parseFrontmatter,
  splitFrontmatter,
} from "./frontmatter";

const FENCE = "---\n";

describe("splitFrontmatter", () => {
  it("splits the header from the body", () => {
    const src = `${FENCE}title: A\norder: 1\nsummary: B\n${FENCE}\n# Heading\n\ntext\n`;
    const { yaml, body } = splitFrontmatter(src);
    expect(yaml).toBe("title: A\norder: 1\nsummary: B");
    expect(body).toBe("\n# Heading\n\ntext\n");
  });

  it("leaves a thematic break inside the body alone", () => {
    // The closing fence is the FIRST `---` after the opening one; a second
    // `---` later in the document is content, not a header.
    const src = `${FENCE}title: A\norder: 1\nsummary: B\n${FENCE}\nintro\n\n---\n\nafter\n`;
    expect(splitFrontmatter(src).body).toBe("\nintro\n\n---\n\nafter\n");
  });

  it("refuses a chapter with no fence and one with an unclosed fence", () => {
    expect(() => splitFrontmatter("# Heading\n")).toThrow(FrontmatterError);
    expect(() => splitFrontmatter(`${FENCE}title: A\n`)).toThrow(/never closed/);
  });

  // Control: the matcher fires on a real fence. Without it, the two rejections
  // above would also pass on a file whose parser never matched anything.
  it("CONTROL: hasFrontmatter is true for a real header and false without one", () => {
    expect(hasFrontmatter(`${FENCE}title: A\n${FENCE}`)).toBe(true);
    expect(hasFrontmatter("# Heading\n")).toBe(false);
  });
});

describe("parseFrontmatter", () => {
  it("reads the scalar fields", () => {
    const fm = parseFrontmatter("title: Why\norder: 3\nsummary: One line\n", "c.mdx");
    expect(fm).toEqual({ title: "Why", order: 3, summary: "One line", draft: false });
  });

  it("unquotes a value and keeps a colon inside it", () => {
    const fm = parseFrontmatter('title: "Read: a guide"\norder: 1\nsummary: s\n', "c.mdx");
    expect(fm.title).toBe("Read: a guide");
  });

  it("folds a block scalar into one line", () => {
    const fm = parseFrontmatter(
      "title: A\norder: 1\nsummary: >-\n  first part\n  second part\n",
      "c.mdx",
    );
    expect(fm.summary).toBe("first part second part");
  });

  it("reads draft as a boolean, not as the string \"true\"", () => {
    expect(parseFrontmatter("title: A\norder: 1\nsummary: s\ndraft: true\n", "c.mdx").draft).toBe(true);
    expect(parseFrontmatter("title: A\norder: 1\nsummary: s\ndraft: false\n", "c.mdx").draft).toBe(false);
  });

  it("names the missing keys", () => {
    expect(() => parseFrontmatter("title: A\n", "c.mdx")).toThrow(/missing order, summary/);
  });

  // Each of these is a silent-default bug if it ever stops throwing: the
  // chapter would ship with a blank title, an unroutable order, or a key the
  // reader pretends to understand.
  it("rejects an unknown key, a non-numeric order and a non-boolean draft", () => {
    expect(() => parseFrontmatter("title: A\norder: 1\nsummary: s\nauthor: me\n", "c.mdx")).toThrow(
      /unknown frontmatter key `author`/,
    );
    expect(() => parseFrontmatter("title: A\norder: first\nsummary: s\n", "c.mdx")).toThrow(
      /`order` must be a number/,
    );
    expect(() => parseFrontmatter("title: A\norder: 1\nsummary: s\ndraft: yes\n", "c.mdx")).toThrow(
      /`draft` must be true or false/,
    );
  });

  it("names the file in the error, so a build failure points at one chapter", () => {
    expect(() => parseFrontmatter("order: 1\n", "content/book/03-wire.mdx")).toThrow(
      /content\/book\/03-wire\.mdx.*missing title, summary/s,
    );
  });
});