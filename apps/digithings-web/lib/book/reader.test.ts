import { describe, expect, it } from "vitest";

import { ownsArrowKeys, pageDelta, scopedId, stepPage, type ReaderPage } from "./reader";

const pages: ReaderPage[] = [
  { id: "cover", number: "", title: "the digithings book" },
  { id: "contents", number: "", title: "contents" },
  { id: "01-why-a-book", number: "01", title: "Why this book exists" },
];

const key = (
  k: string,
  mods: Partial<Record<"altKey" | "ctrlKey" | "metaKey" | "shiftKey", boolean>> = {},
) => ({
  key: k,
  altKey: false,
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  ...mods,
});

describe("stepPage", () => {
  it("moves forward and back", () => {
    expect(stepPage(pages, "contents", 1)?.id).toBe("01-why-a-book");
    expect(stepPage(pages, "contents", -1)?.id).toBe("cover");
  });

  it("stops at either end of the book", () => {
    expect(stepPage(pages, "cover", -1)?.id).toBe("cover");
    expect(stepPage(pages, "01-why-a-book", 1)?.id).toBe("01-why-a-book");
  });

  it("starts from the cover when the current page is unknown", () => {
    expect(stepPage(pages, "nope", 1)?.id).toBe("contents");
    expect(stepPage([], "cover", 1)).toBeNull();
  });
});

describe("pageDelta", () => {
  it("turns pages on the left and right arrows only", () => {
    expect(pageDelta(key("ArrowRight"))).toBe(1);
    expect(pageDelta(key("ArrowLeft"))).toBe(-1);
    expect(pageDelta(key("ArrowDown"))).toBe(0);
  });

  it("leaves modified arrows to the browser", () => {
    expect(pageDelta(key("ArrowRight", { metaKey: true }))).toBe(0);
    expect(pageDelta(key("ArrowLeft", { altKey: true }))).toBe(0);
    expect(pageDelta(key("ArrowRight", { shiftKey: true }))).toBe(0);
  });
});

describe("ownsArrowKeys", () => {
  it("treats anything without closest() as not typing", () => {
    expect(ownsArrowKeys(null)).toBe(false);
    expect(ownsArrowKeys({} as EventTarget)).toBe(false);
  });

  it("leaves arrows to fields, widgets and focusable scroll containers", () => {
    const seen: string[] = [];
    const probe = {
      closest: (selector: string) => (seen.push(selector), null),
    } as unknown as EventTarget;
    ownsArrowKeys(probe);
    const selector = seen[0] ?? "";
    for (const part of [
      "input",
      "textarea",
      "[role='slider']",
      "[role='tab']",
      "video",
      "[tabindex]:not([tabindex='-1'])",
    ]) {
      expect(selector).toContain(part);
    }
  });

  it("asks the element whether it sits in a field", () => {
    const inField = { closest: () => ({}) } as unknown as EventTarget;
    const outside = { closest: () => null } as unknown as EventTarget;
    expect(ownsArrowKeys(inField)).toBe(true);
    expect(ownsArrowKeys(outside)).toBe(false);
  });
});

describe("scopedId", () => {
  it("prefixes heading ids with the chapter so repeated headings stay unique", () => {
    expect(scopedId("10-digigraph", "how-it-works")).toBe("10-digigraph--how-it-works");
    expect(scopedId("11-digillm", "how-it-works")).not.toBe(
      scopedId("10-digigraph", "how-it-works"),
    );
    expect(scopedId("10-digigraph", undefined)).toBeUndefined();
  });
});
