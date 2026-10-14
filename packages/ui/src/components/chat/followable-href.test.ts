import { describe, expect, it } from "vitest";
import { isFollowableHref } from "./followable-href";

describe("isFollowableHref", () => {
  it("links web, mail, anchors and site paths only", () => {
    for (const ok of ["https://help.example.com/a", "http://x.y", "mailto:a@b.c", "#top", "/docs"]) {
      expect(isFollowableHref(ok)).toBe(true);
    }
    for (const no of [undefined, "", "repo://occ/manual.md", "javascript:alert(1)", "//evil.example", "clients/occ/note"]) {
      expect(isFollowableHref(no)).toBe(false);
    }
  });
});
