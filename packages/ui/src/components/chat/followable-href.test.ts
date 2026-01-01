import { describe, expect, it } from "vitest";
import { isFollowableHref } from "./followable-href";

describe("isFollowableHref", () => {
  it("links web, mail, anchors and site paths only", () => {
    for (const ok of ["https://help.example.com/a", "http://x.y", "mailto:a@b.c", "#top", "/docs"]) {
      expect(isFollowableHref(ok)).toBe(true);
    }
    for (const no of [undefined, "", "repo://tenantb/manual.md", "javascript:alert(1)", "//evil.example", "clients/tenantb/note"]) {
      expect(isFollowableHref(no)).toBe(false);
    }
  });
});
