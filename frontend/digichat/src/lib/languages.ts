/**
 * Response-language allowlist for digichat `/language` (#3733).
 * Kept in exact sync with digigraph's `digigraph.languages.LANGUAGE_NAMES` —
 * see `tests/dg/test_languages.py`. Unknown / crafted values never reach a
 * prompt: only these display names are interpolated server-side.
 */
export const LANGUAGES: { code: string; label: string }[] = [
  { code: "af", label: "Afrikaans" },
  { code: "ar", label: "Arabic" },
  { code: "bg", label: "Bulgarian" },
  { code: "bn", label: "Bengali" },
  { code: "ca", label: "Catalan" },
  { code: "cs", label: "Czech" },
  { code: "da", label: "Danish" },
  { code: "de", label: "German" },
  { code: "el", label: "Greek" },
  { code: "en", label: "English" },
  { code: "es", label: "Spanish" },
  { code: "et", label: "Estonian" },
  { code: "fa", label: "Persian" },
  { code: "fi", label: "Finnish" },
  { code: "fr", label: "French" },
  { code: "ga", label: "Irish" },
  { code: "he", label: "Hebrew" },
  { code: "hi", label: "Hindi" },
  { code: "hr", label: "Croatian" },
  { code: "hu", label: "Hungarian" },
  { code: "id", label: "Indonesian" },
  { code: "is", label: "Icelandic" },
  { code: "it", label: "Italian" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
  { code: "lt", label: "Lithuanian" },
  { code: "lv", label: "Latvian" },
  { code: "ms", label: "Malay" },
  { code: "nl", label: "Dutch" },
  { code: "no", label: "Norwegian" },
  { code: "pl", label: "Polish" },
  { code: "pt", label: "Portuguese" },
  { code: "ro", label: "Romanian" },
  { code: "ru", label: "Russian" },
  { code: "sk", label: "Slovak" },
  { code: "sl", label: "Slovenian" },
  { code: "sr", label: "Serbian" },
  { code: "sv", label: "Swedish" },
  { code: "sw", label: "Swahili" },
  { code: "ta", label: "Tamil" },
  { code: "th", label: "Thai" },
  { code: "tr", label: "Turkish" },
  { code: "uk", label: "Ukrainian" },
  { code: "ur", label: "Urdu" },
  { code: "vi", label: "Vietnamese" },
  { code: "zh", label: "Chinese" },
];

/** Slash / settings submenu — not the full map. */
export const FEATURED_LANGUAGE_CODES = ["en", "nl", "it", "es", "fr"] as const;

export const DEFAULT_LANGUAGE_CODE = "en";

const KNOWN_CODES = new Set(LANGUAGES.map((l) => l.code));

const LABEL_TO_CODE = new Map(
  LANGUAGES.map((l) => [l.label.toLowerCase(), l.code] as const),
);

/** Extra English / native names that are not the canonical label. */
const LANGUAGE_ALIASES: Readonly<Record<string, string>> = {
  nederlands: "nl",
  dutch: "nl",
  german: "de",
  deutsch: "de",
  spanish: "es",
  espanol: "es",
  italian: "it",
  italiano: "it",
  french: "fr",
  francais: "fr",
  portuguese: "pt",
  portugues: "pt",
  japanese: "ja",
  chinese: "zh",
  mandarin: "zh",
  korean: "ko",
  arabic: "ar",
};

/**
 * Map a typed name, alias, or BCP-47 tag onto a curated code.
 * Returns null when the input is not in the allowlist — never a guess that
 * would send unknown text upstream.
 */
export function tryResolveLanguageInput(
  input: string | null | undefined,
): string | null {
  const raw = (input ?? "").trim().toLowerCase();
  if (!raw) return null;
  const primary = raw.split(/[-_]/)[0] ?? raw;
  if (KNOWN_CODES.has(primary)) return primary;
  if (LANGUAGE_ALIASES[raw]) return LANGUAGE_ALIASES[raw];
  if (LANGUAGE_ALIASES[primary]) return LANGUAGE_ALIASES[primary];
  const fromLabel = LABEL_TO_CODE.get(raw);
  return fromLabel ?? null;
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
