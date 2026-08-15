import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_LANGUAGE_CODE,
  LANGUAGES,
  detectBrowserLanguageCode,
  resolveLanguageCode,
} from "@/lib/languages";

describe("LANGUAGES", () => {
  it("is the curated 5-language list", () => {
    expect(LANGUAGES).toEqual([
      { code: "en", label: "English" },
      { code: "de", label: "German" },
      { code: "it", label: "Italian" },
      { code: "es", label: "Spanish" },
      { code: "fr", label: "French" },
    ]);
  });
});

describe("resolveLanguageCode", () => {
  it("passes through a known lowercase code", () => {
    expect(resolveLanguageCode("de")).toBe("de");
  });

  it("lowercases a known code", () => {
    expect(resolveLanguageCode("DE")).toBe("de");
  });

  it.each([null, undefined, "", "  ", "xx", "klingon", "<script>"])(
    "falls back to English for %p",
    (bad) => {
      expect(resolveLanguageCode(bad)).toBe(DEFAULT_LANGUAGE_CODE);
    },
  );
});

describe("detectBrowserLanguageCode", () => {
  it("matches a curated language from navigator.language", () => {
    vi.stubGlobal("navigator", { language: "de-DE" });
    expect(detectBrowserLanguageCode()).toBe("de");
    vi.unstubAllGlobals();
  });

  it("falls back to English for an uncurated browser locale", () => {
    vi.stubGlobal("navigator", { language: "ja-JP" });
    expect(detectBrowserLanguageCode()).toBe("en");
    vi.unstubAllGlobals();
  });

  it("falls back to English when navigator is unavailable", () => {
    vi.stubGlobal("navigator", undefined);
    expect(detectBrowserLanguageCode()).toBe("en");
    vi.unstubAllGlobals();
  });
});
