import { describe, expect, it } from "vitest";

import { BRIEF, briefChapters } from "./brief";
import { loadChapters } from "./chapters.server";

const ROOT = process.cwd();

describe("the brief edition", () => {
  it("names every chapter once, and every one is published", () => {
    expect(new Set(BRIEF).size).toBe(BRIEF.length);
    const chapters = briefChapters(loadChapters(ROOT));
    expect(chapters.map((c) => c.slug)).toEqual([...BRIEF]);
  });

  it("keeps the editorial order, not the source order", () => {
    const slugs = briefChapters([...BRIEF].reverse().map((slug) => ({ slug }))).map((c) => c.slug);
    expect(slugs).toEqual([...BRIEF]);
  });

  it("refuses a slug with no chapter behind it", () => {
    expect(() => briefChapters([{ slug: "01-why-a-book" }])).toThrow(/is not a published chapter/);
  });
});
