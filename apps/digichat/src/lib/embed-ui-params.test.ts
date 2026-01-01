import { describe, expect, it } from "vitest";
import { readEmbedUiParams } from "./embed-ui-params";

describe("readEmbedUiParams", () => {
  it("parses welcome and placeholder", () => {
    expect(
      readEmbedUiParams("?welcome=Hello&placeholder=Ask%20me"),
    ).toEqual({ welcome: "Hello", placeholder: "Ask me" });
  });

  it("parses pipe-separated suggestions", () => {
    expect(readEmbedUiParams("?suggestions=one|two|three")).toEqual({
      suggestions: ["one", "two", "three"],
    });
  });

  it("parses JSON suggestions array", () => {
    expect(readEmbedUiParams('?suggestions=["a","b"]')).toEqual({
      suggestions: ["a", "b"],
    });
  });

  it("parses a valid hex accent and foreground", () => {
    expect(
      readEmbedUiParams("?accent=%23f5a623&accentForeground=%23ffffff"),
    ).toEqual({ accent: "#f5a623", accentForeground: "#ffffff" });
  });

  it("starts private mode only for an exact 1 (ON-only, like wide)", () => {
    expect(readEmbedUiParams("?private=1").privateMode).toBe(true);
    expect(readEmbedUiParams("?private=0").privateMode).toBeUndefined();
    expect(readEmbedUiParams("?private=true").privateMode).toBeUndefined();
    expect(readEmbedUiParams("?private").privateMode).toBeUndefined();
    expect(readEmbedUiParams("").privateMode).toBeUndefined();
  });
});
