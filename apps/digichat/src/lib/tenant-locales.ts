/**
 * Per-tenant chat languages (the composer language chip).
 *
 * A tenant row may list the languages its chat offers and the translated
 * copy for each one:
 *
 *   "locales": {
 *     "languages": ["en", "fr"],
 *     "strings": { "fr": { "welcome": "…", "placeholder": "…", "suggestions": ["…"] } }
 *   }
 *
 * The first language is the tenant default; its copy is the row's own
 * `welcome` / `placeholder` / `suggestions` / `welcomeBody`. Another language
 * swaps in its strings field by field and keeps the default for anything it
 * leaves out. The answer language rides the existing `/language` preference
 * (X-Digi-Language), so the chip and `/language` are one setting.
 *
 * A tenant without `locales` is unchanged: no chip, no browser detection, no
 * stored choice.
 */

import { LANGUAGES, tryResolveLanguageInput } from "@/lib/languages";

export type TenantCredit = { lead: string; tail: string };

export type TenantLocaleStrings = {
  welcome?: string;
  welcomeBody?: string[];
  placeholder?: string;
  suggestions?: string[];
  /** Footer credit around the "digithings" link: `${lead} digithings ${tail}`. */
  credit?: TenantCredit;
};

export type TenantLocales = {
  languages: string[];
  strings?: Record<string, TenantLocaleStrings>;
};

export const MAX_TENANT_LANGUAGES = 8;

function stringList(value: unknown, where: string): string[] {
  if (!Array.isArray(value) || value.some((x) => typeof x !== "string")) {
    throw new Error(`${where} must be an array of strings`);
  }
  return (value as string[]).map((s) => s.trim()).filter(Boolean);
}

function optionalString(value: unknown, where: string): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string") throw new Error(`${where} must be a string`);
  return value;
}

/** Validates a row's `locales`; throws with `ctx` on a bad shape. */
export function parseTenantLocales(value: unknown, ctx: string): TenantLocales | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${ctx}: locales must be an object`);
  }
  const v = value as Record<string, unknown>;
  const raw = stringList(v.languages, `${ctx}: locales.languages`);
  const languages: string[] = [];
  for (const entry of raw) {
    const code = tryResolveLanguageInput(entry);
    if (!code) throw new Error(`${ctx}: locales.languages has an unknown language "${entry}"`);
    if (!languages.includes(code)) languages.push(code);
  }
  if (languages.length < 1 || languages.length > MAX_TENANT_LANGUAGES) {
    throw new Error(`${ctx}: locales.languages must list 1 to ${MAX_TENANT_LANGUAGES} languages`);
  }
  let strings: Record<string, TenantLocaleStrings> | undefined;
  if (v.strings !== undefined) {
    if (typeof v.strings !== "object" || v.strings === null || Array.isArray(v.strings)) {
      throw new Error(`${ctx}: locales.strings must be an object`);
    }
    strings = {};
    for (const [key, entry] of Object.entries(v.strings as Record<string, unknown>)) {
      const code = tryResolveLanguageInput(key);
      if (!code || !languages.includes(code)) {
        throw new Error(`${ctx}: locales.strings.${key} is not one of locales.languages`);
      }
      if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
        throw new Error(`${ctx}: locales.strings.${key} must be an object`);
      }
      const e = entry as Record<string, unknown>;
      const where = `${ctx}: locales.strings.${key}`;
      const out: TenantLocaleStrings = {};
      const welcome = optionalString(e.welcome, `${where}.welcome`);
      if (welcome !== undefined) out.welcome = welcome;
      const placeholder = optionalString(e.placeholder, `${where}.placeholder`);
      if (placeholder !== undefined) out.placeholder = placeholder;
      if (e.welcomeBody !== undefined) out.welcomeBody = stringList(e.welcomeBody, `${where}.welcomeBody`);
      if (e.suggestions !== undefined) out.suggestions = stringList(e.suggestions, `${where}.suggestions`);
      if (e.credit !== undefined) {
        const c = e.credit as Record<string, unknown> | null;
        if (!c || typeof c.lead !== "string" || typeof c.tail !== "string") {
          throw new Error(`${where}.credit must be { lead, tail } strings`);
        }
        out.credit = { lead: c.lead, tail: c.tail };
      }
      strings[code] = out;
    }
  }
  return strings ? { languages, strings } : { languages };
}

/**
 * The language a first visit lands on: the first browser language that is one
 * of the tenant's other languages (any `fr*` picks `fr`), else the default.
 */
export function pickBrowserLanguage(
  browser: readonly string[] | undefined,
  locales: TenantLocales,
): string {
  const [fallback, ...others] = locales.languages;
  for (const tag of browser ?? []) {
    const primary = tag.toLowerCase().split(/[-_]/)[0] ?? "";
    if (others.includes(primary)) return primary;
  }
  return fallback;
}

export function languageChoiceKey(slug: string): string {
  return `dt-language:${slug}`;
}

/** A stored explicit choice wins over the browser, if the tenant still offers it. */
export function resolveTenantLanguage(
  locales: TenantLocales,
  stored: string | null | undefined,
  browser: readonly string[] | undefined,
): string {
  if (stored && locales.languages.includes(stored)) return stored;
  return pickBrowserLanguage(browser, locales);
}

type LocalizableCopy = {
  welcome?: string;
  welcomeBody?: string[];
  placeholder?: string;
  suggestions?: string[];
  locales?: TenantLocales;
};

/** The row's copy in `language`; the default language (or no locales) returns `cfg` itself. */
export function localizeTenantCopy<T extends LocalizableCopy>(cfg: T, language: string): T {
  const strings = cfg.locales?.strings?.[language];
  if (!strings || language === cfg.locales?.languages[0]) return cfg;
  return {
    ...cfg,
    ...(strings.welcome !== undefined ? { welcome: strings.welcome } : {}),
    ...(strings.welcomeBody !== undefined ? { welcomeBody: strings.welcomeBody } : {}),
    ...(strings.placeholder !== undefined ? { placeholder: strings.placeholder } : {}),
    ...(strings.suggestions !== undefined ? { suggestions: strings.suggestions } : {}),
  };
}

export function tenantCredit(
  locales: TenantLocales | undefined,
  language: string,
): TenantCredit | undefined {
  return locales?.strings?.[language]?.credit;
}

/** Chip rows: short code + autonym, in the tenant's order. */
export function tenantLanguageOptions(
  locales: TenantLocales | undefined,
): { code: string; short: string; label: string }[] | undefined {
  if (!locales || locales.languages.length < 2) return undefined;
  return locales.languages.map((code) => ({
    code,
    short: code.toUpperCase(),
    label: LANGUAGES.find((l) => l.code === code)?.native ?? code,
  }));
}
