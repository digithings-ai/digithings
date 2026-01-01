/** Pure trace i18n core: tables, plural rules, no React. */
import { en } from "./locales/en";
import { fr } from "./locales/fr";
import type { TracePluralKey, TraceStringKey, TraceStrings } from "./types";

/** Registered trace tables. A language without a table falls back to English. */
export const TRACE_LOCALES: Readonly<Record<string, TraceStrings>> = { en, fr };

export const DEFAULT_TRACE_LOCALE = "en";

function primary(locale: string | null | undefined): string {
  return (locale ?? "").split(/[-_]/)[0]?.toLowerCase() ?? "";
}

export function resolveTraceLocale(locale: string | null | undefined): string {
  const code = primary(locale);
  return TRACE_LOCALES[code] ? code : DEFAULT_TRACE_LOCALE;
}

export type TraceT = {
  locale: string;
  t: (key: TraceStringKey, vars?: Record<string, string>) => string;
  plural: (key: TracePluralKey, count: number) => string;
};

function fill(text: string, vars?: Record<string, string>): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, k: string) => vars[k] ?? m);
}

export function createTraceT(locale: string | null | undefined): TraceT {
  const code = resolveTraceLocale(locale);
  const table = TRACE_LOCALES[code] ?? en;
  const rules = new Intl.PluralRules(code);
  const num = new Intl.NumberFormat(code);
  return {
    locale: code,
    t: (key, vars) => fill(table[key] ?? en[key], vars),
    plural: (key, count) => {
      const msg = table[key] ?? en[key];
      const text = msg[rules.select(count)] ?? msg.other;
      return fill(text, { count: num.format(count) });
    },
  };
}

/** Default English helper for pure functions called without a hook. */
export const EN_TRACE_T: TraceT = createTraceT(DEFAULT_TRACE_LOCALE);
