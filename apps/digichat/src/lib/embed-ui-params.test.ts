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

  it("ignores a non-hex / malformed accent (never lets it reach a CSS var)", () => {
    expect(readEmbedUiParams("?accent=red").accent).toBeUndefined();
    expect(readEmbedUiParams("?accent=%23fff").accent).toBeUndefined();
    expect(readEmbedUiParams("?accent=javascript:alert(1)").accent).toBeUndefined();
  });
});
