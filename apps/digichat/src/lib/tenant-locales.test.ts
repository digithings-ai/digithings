import { describe, expect, it } from "vitest";
import {
  localizeTenantCopy,
  parseTenantLocales,
  pickBrowserLanguage,
  resolveTenantLanguage,
  tenantCredit,
  tenantLanguageOptions,
} from "./tenant-locales";

const locales = parseTenantLocales(
  {
    languages: ["en", "Français"],
    strings: { fr: { welcome: "Bonjour", placeholder: "Posez une question", suggestions: ["Q ?"], credit: { lead: "propulsé par digichat, un produit", tail: "." } } },
  },
  "t",
)!;

describe("tenant locales", () => {
  it("parses codes, autonyms and strings", () => {
    expect(locales.languages).toEqual(["en", "fr"]);
    expect(locales.strings?.fr?.welcome).toBe("Bonjour");
  });
  it("rejects unknown languages and strings for unlisted languages", () => {
    expect(() => parseTenantLocales({ languages: ["xx"] }, "t")).toThrow(/unknown language/);
    expect(() => parseTenantLocales({ languages: ["en"], strings: { fr: {} } }, "t")).toThrow(/not one of/);
    expect(() => parseTenantLocales({ languages: [] }, "t")).toThrow(/1 to 8/);
  });
  it("any fr* browser language lands in French, else the default", () => {
    expect(pickBrowserLanguage(["fr-CA", "en"], locales)).toBe("fr");
    expect(pickBrowserLanguage(["en-US", "fr-FR"], locales)).toBe("fr");
    expect(pickBrowserLanguage(["en-US"], locales)).toBe("en");
    expect(pickBrowserLanguage(["de-DE"], locales)).toBe("en");
    expect(pickBrowserLanguage(undefined, locales)).toBe("en");
  });
  it("a stored explicit choice wins over the browser, if still offered", () => {
    expect(resolveTenantLanguage(locales, "en", ["fr-CA"])).toBe("en");
    expect(resolveTenantLanguage(locales, "it", ["fr-CA"])).toBe("fr");
  });
  it("localizes copy field by field; the default language and no-locale tenants are untouched", () => {
    const cfg = { welcome: "Hi", placeholder: "Ask", suggestions: ["Q?"], locales };
    expect(localizeTenantCopy(cfg, "en")).toBe(cfg);
    expect(localizeTenantCopy(cfg, "fr")).toMatchObject({ welcome: "Bonjour", placeholder: "Posez une question", suggestions: ["Q ?"] });
    const plain = { welcome: "Hi" };
    expect(localizeTenantCopy(plain, "fr")).toBe(plain);
  });
  it("chip options need two languages; credit follows the language", () => {
    expect(tenantLanguageOptions(locales)?.map((o) => o.short)).toEqual(["EN", "FR"]);
    expect(tenantLanguageOptions(parseTenantLocales({ languages: ["en"] }, "t"))).toBeUndefined();
    expect(tenantLanguageOptions(undefined)).toBeUndefined();
    expect(tenantCredit(locales, "fr")?.lead).toMatch(/^propulsé/);
    expect(tenantCredit(locales, "en")).toBeUndefined();
  });
});
