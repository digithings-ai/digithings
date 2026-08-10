import { describe, expect, it } from "vitest";
import { hashIdFromHref, isSamePageHashHref } from "./hashScroll";

const HOME = "https://digiquant.io/";

describe("isSamePageHashHref", () => {
  it("matches hash links on the same path", () => {
    expect(isSamePageHashHref("/#strategies", HOME)).toBe(true);
    expect(isSamePageHashHref("#pipeline", `${HOME}#hero`)).toBe(true);
  });

  it("rejects cross-page hash links", () => {
    expect(isSamePageHashHref("/pricing#top", HOME)).toBe(false);
    expect(isSamePageHashHref("https://digithings.ai/#architecture", HOME)).toBe(false);
  });

  it("rejects external and non-hash links", () => {
    expect(isSamePageHashHref("https://github.com/digithings-ai", HOME)).toBe(false);
    expect(isSamePageHashHref("/strategies", HOME)).toBe(false);
  });
});

describe("hashIdFromHref", () => {
  it("extracts the target id", () => {
    expect(hashIdFromHref("/#strategies", HOME)).toBe("strategies");
    expect(hashIdFromHref("/#pricing", HOME)).toBe("pricing");
  });
});
