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
});
