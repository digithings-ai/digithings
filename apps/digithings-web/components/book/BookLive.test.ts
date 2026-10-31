import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(path.join(__dirname, "BookLive.tsx"), "utf8");

describe("BookLive", () => {
  it("marks the reader ready only after pagination allows the column scale", () => {
    // .book-live[data-ready] is the line the export guard waits on. The stage
    // stays untransformed until <html data-book-paginated>, and the scale that
    // follows shrinks it from 794px to the column. Ready has to come after that
    // marker: the page boxes stay hidden until ready, so the shrink is over
    // before the guard measures and pressing PDF does not move the stage.
    const marker = source.indexOf("document.documentElement.dataset.bookPaginated");
    const ready = source.indexOf("setReady(true)");
    expect(marker).toBeGreaterThan(-1);
    expect(ready).toBeGreaterThan(marker);
    expect(source.slice(marker, ready)).toContain("&& paginated");
    expect(source).toContain('paged ? `scale(${scale})` : "none"');
  });
});
