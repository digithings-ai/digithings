import { describe, expect, it } from "vitest";
import {
  DEFAULT_SCROLL_MODE,
  normalizeScrollMode,
  readStoredScrollMode,
  resolveScrollMode,
  scrollModeProps,
  writeStoredScrollMode,
} from "./scroll-mode";

describe("scroll mode", () => {
  it("defaults to follow", () => {
    expect(DEFAULT_SCROLL_MODE).toBe("follow");
    expect(resolveScrollMode(undefined, undefined)).toBe("follow");
  });

  it("keeps a stored choice over the deployment default", () => {
    expect(resolveScrollMode("free", "follow")).toBe("free");
    expect(resolveScrollMode("follow", "free")).toBe("follow");
    expect(resolveScrollMode(undefined, "free")).toBe("free");
  });

  it("ignores a value that is not a mode", () => {
    expect(normalizeScrollMode("nope")).toBeUndefined();
    expect(normalizeScrollMode(null)).toBeUndefined();
    expect(resolveScrollMode("roomy", "wide")).toBe("follow");
  });

  it("follow reads the anchor and every scroll trigger on", () => {
    expect(scrollModeProps("follow")).toEqual({
      turnAnchor: "top",
      autoScroll: true,
      scrollToBottomOnRunStart: true,
      scrollToBottomOnInitialize: true,
      scrollToBottomOnThreadSwitch: true,
    });
  });

  it("free turns every trigger off and drops the anchor", () => {
    expect(scrollModeProps("free")).toEqual({
      turnAnchor: "bottom",
      autoScroll: false,
      scrollToBottomOnRunStart: false,
      scrollToBottomOnInitialize: false,
      scrollToBottomOnThreadSwitch: false,
    });
  });

  it("an absent mode behaves like follow", () => {
    expect(scrollModeProps(undefined)).toEqual(scrollModeProps("follow"));
  });

  it("reads and writes the stored choice", () => {
    expect(readStoredScrollMode({ getItem: () => "free" })).toBe("free");
    expect(readStoredScrollMode({ getItem: () => "wide" })).toBeUndefined();
    expect(readStoredScrollMode({ getItem: () => null })).toBeUndefined();
    expect(readStoredScrollMode(null)).toBeUndefined();
  });

  it("survives storage that throws", () => {
    expect(
      readStoredScrollMode({
        getItem: () => {
          throw new Error("blocked");
        },
      }),
    ).toBeUndefined();
  });
});
