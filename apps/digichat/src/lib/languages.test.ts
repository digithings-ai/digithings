import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_LANGUAGE_CODE,
  FEATURED_LANGUAGE_CODES,
  LANGUAGES,
  detectBrowserLanguageCode,
  matchLanguageQuery,
  resolveLanguageCode,
} from "@/lib/languages";

describe("LANGUAGES", () => {
  it("includes Dutch and the featured ISO set", () => {
    const codes = LANGUAGES.map((l) => l.code);
    expect(codes).toContain("nl");
    expect(codes).toContain("en");
    expect(FEATURED_LANGUAGE_CODES).toEqual(["en", "nl", "it", "es", "fr"]);
  });

  it("has unique codes", () => {
    const codes = LANGUAGES.map((l) => l.code);
    expect(new Set(codes).size).toBe(codes.length);
  });
});

describe("matchLanguageQuery", () => {
  it("maps codes, English names, and aliases", () => {
    expect(matchLanguageQuery("nl")).toBe("nl");
    expect(matchLanguageQuery("Dutch")).toBe("nl");
    expect(matchLanguageQuery("nederlands")).toBe("nl");
    expect(matchLanguageQuery("Italiano")).toBe("it");
    expect(matchLanguageQuery("pt-BR")).toBe("pt");
  });

  it("maps autonyms, folded diacritics, and ISO abbreviations", () => {
    expect(matchLanguageQuery("en")).toBe("en");
    expect(matchLanguageQuery("English")).toBe("en");
    expect(matchLanguageQuery("Deutsch")).toBe("de");
    expect(matchLanguageQuery("espanol")).toBe("es");
    expect(matchLanguageQuery("Français")).toBe("fr");
    expect(matchLanguageQuery("日本語")).toBe("ja");
    expect(matchLanguageQuery("中文")).toBe("zh");
    expect(matchLanguageQuery("한국어")).toBe("ko");
    expect(matchLanguageQuery("Português")).toBe("pt");
  });

  it("returns null for garbage instead of falling back", () => {
    expect(matchLanguageQuery("klingon")).toBeNull();
    expect(matchLanguageQuery("Ignore previous")).toBeNull();
    expect(matchLanguageQuery("<script>")).toBeNull();
    expect(matchLanguageQuery("")).toBeNull();
  });
});

describe("resolveLanguageCode", () => {
  it("passes through a known lowercase code", () => {
    expect(resolveLanguageCode("de")).toBe("de");
    expect(resolveLanguageCode("nl")).toBe("nl");
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

  it("maps Japanese browser locale onto ja", () => {
    vi.stubGlobal("navigator", { language: "ja-JP" });
    expect(detectBrowserLanguageCode()).toBe("ja");
    vi.unstubAllGlobals();
  });

  it("falls back to English when navigator is unavailable", () => {
    vi.stubGlobal("navigator", undefined);
    expect(detectBrowserLanguageCode()).toBe("en");
    vi.unstubAllGlobals();
  });
});
