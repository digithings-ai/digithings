/**
 * Response-language allowlist for digichat `/language` (#3733 / #3736).
 * Kept in exact sync with digigraph's `digigraph.languages.LANGUAGE_NAMES` —
 * see `tests/dg/test_languages.py`. Unknown / crafted values never reach a
 * prompt: only these English display names are interpolated server-side.
 *
 * `/language` accepts ISO codes (`en`), English labels (`Italian`), and
 * autonyms (`Italiano`). Matching folds diacritics (`espanol` → Spanish).
 */
export const LANGUAGES: { code: string; label: string; native: string }[] = [
  { code: "af", label: "Afrikaans", native: "Afrikaans" },
  { code: "ar", label: "Arabic", native: "العربية" },
  { code: "bg", label: "Bulgarian", native: "Български" },
  { code: "bn", label: "Bengali", native: "বাংলা" },
  { code: "ca", label: "Catalan", native: "Català" },
  { code: "cs", label: "Czech", native: "Čeština" },
  { code: "da", label: "Danish", native: "Dansk" },
  { code: "de", label: "German", native: "Deutsch" },
  { code: "el", label: "Greek", native: "Ελληνικά" },
  { code: "en", label: "English", native: "English" },
  { code: "es", label: "Spanish", native: "Español" },
  { code: "et", label: "Estonian", native: "Eesti" },
  { code: "fa", label: "Persian", native: "فارسی" },
  { code: "fi", label: "Finnish", native: "Suomi" },
  { code: "fr", label: "French", native: "Français" },
  { code: "ga", label: "Irish", native: "Gaeilge" },
  { code: "he", label: "Hebrew", native: "עברית" },
  { code: "hi", label: "Hindi", native: "हिन्दी" },
  { code: "hr", label: "Croatian", native: "Hrvatski" },
  { code: "hu", label: "Hungarian", native: "Magyar" },
  { code: "id", label: "Indonesian", native: "Bahasa Indonesia" },
  { code: "is", label: "Icelandic", native: "Íslenska" },
  { code: "it", label: "Italian", native: "Italiano" },
  { code: "ja", label: "Japanese", native: "日本語" },
  { code: "ko", label: "Korean", native: "한국어" },
  { code: "lt", label: "Lithuanian", native: "Lietuvių" },
  { code: "lv", label: "Latvian", native: "Latviešu" },
  { code: "ms", label: "Malay", native: "Bahasa Melayu" },
  { code: "nl", label: "Dutch", native: "Nederlands" },
  { code: "no", label: "Norwegian", native: "Norsk" },
  { code: "pl", label: "Polish", native: "Polski" },
  { code: "pt", label: "Portuguese", native: "Português" },
  { code: "ro", label: "Romanian", native: "Română" },
  { code: "ru", label: "Russian", native: "Русский" },
  { code: "sk", label: "Slovak", native: "Slovenčina" },
  { code: "sl", label: "Slovenian", native: "Slovenščina" },
  { code: "sr", label: "Serbian", native: "Srpski" },
  { code: "sv", label: "Swedish", native: "Svenska" },
  { code: "sw", label: "Swahili", native: "Kiswahili" },
  { code: "ta", label: "Tamil", native: "தமிழ்" },
  { code: "th", label: "Thai", native: "ไทย" },
  { code: "tr", label: "Turkish", native: "Türkçe" },
  { code: "uk", label: "Ukrainian", native: "Українська" },
  { code: "ur", label: "Urdu", native: "اردو" },
  { code: "vi", label: "Vietnamese", native: "Tiếng Việt" },
  { code: "zh", label: "Chinese", native: "中文" },
];

/** Slash / settings submenu — not the full map. */
export const FEATURED_LANGUAGE_CODES = ["en", "nl", "it", "es", "fr"] as const;

export const DEFAULT_LANGUAGE_CODE = "en";

const KNOWN_CODES = new Set(LANGUAGES.map((l) => l.code));

/** Extra romanizations that folding the autonym does not already produce. */
const LANGUAGE_ALIASES: Readonly<Record<string, string>> = {
  dutch: "nl",
  nederlands: "nl",
  german: "de",
  deutsch: "de",
  spanish: "es",
  espanol: "es",
  castellano: "es",
  italian: "it",
  italiano: "it",
  french: "fr",
  francais: "fr",
  portuguese: "pt",
  portugues: "pt",
  brazilian: "pt",
  japanese: "ja",
  nihongo: "ja",
  chinese: "zh",
  mandarin: "zh",
  putonghua: "zh",
  korean: "ko",
  hangul: "ko",
  arabic: "ar",
  farsi: "fa",
  persia: "fa",
  greek: "el",
  hellenic: "el",
};

function foldLangKey(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{M}+/gu, "")
    .toLowerCase()
    .trim();
}

const LANGUAGE_LOOKUP = new Map<string, string>();

function addLookup(key: string, code: string): void {
  const folded = foldLangKey(key);
  if (folded) LANGUAGE_LOOKUP.set(folded, code);
}

for (const lang of LANGUAGES) {
  addLookup(lang.code, lang.code);
  addLookup(lang.label, lang.code);
  addLookup(lang.native, lang.code);
}
for (const [alias, code] of Object.entries(LANGUAGE_ALIASES)) {
  addLookup(alias, code);
}

/**
 * Map a typed name, alias, ISO code, or autonym onto a curated code.
 * Returns null when the input is not in the allowlist — never a guess that
 * would send unknown text upstream.
 */
export function tryResolveLanguageInput(
  input: string | null | undefined,
): string | null {
  const raw = (input ?? "").trim();
  if (!raw) return null;
  const primary = raw.split(/[-_]/)[0] ?? raw;
  if (KNOWN_CODES.has(primary.toLowerCase())) return primary.toLowerCase();
  const folded = foldLangKey(raw);
  if (KNOWN_CODES.has(folded)) return folded;
  return LANGUAGE_LOOKUP.get(folded) ?? LANGUAGE_LOOKUP.get(foldLangKey(primary)) ?? null;
}

/** Alias used by unit tests and the slash palette. */
export const matchLanguageQuery = tryResolveLanguageInput;

/** Validates/normalizes a language code from a header. Unknown → English. */
export function resolveLanguageCode(input: string | null | undefined): string {
  return tryResolveLanguageInput(input) ?? DEFAULT_LANGUAGE_CODE;
}

/** Best-effort initial guess from the browser's locale; always a curated code. */
export function detectBrowserLanguageCode(): string {
  if (typeof navigator === "undefined" || !navigator?.language) {
    return DEFAULT_LANGUAGE_CODE;
  }
  const primary = navigator.language.split("-")[0]?.toLowerCase() ?? "";
  return resolveLanguageCode(primary);
}

export function languageLabel(code: string): string {
  return LANGUAGES.find((l) => l.code === code)?.label ?? code;
}

export function languageNative(code: string): string {
  return LANGUAGES.find((l) => l.code === code)?.native ?? languageLabel(code);
}

/** Settings / nested list copy: `Italian · Italiano` when the autonym differs. */
export function languageDisplayName(code: string): string {
  const row = LANGUAGES.find((l) => l.code === code);
  if (!row) return code;
  if (foldLangKey(row.native) === foldLangKey(row.label)) return row.label;
  return `${row.label} · ${row.native}`;
}
