/**
 * Curated response-language list for DigiChat's language selector (#2103).
 * Kept in exact sync with digigraph's `digigraph.languages.LANGUAGE_NAMES` —
 * see `tests/dg/test_languages.py` on the Python side and this file's test
 * for the codes; there is no shared module across the two languages, so any
 * change here must be mirrored there by hand.
 */
export const LANGUAGES: { code: string; label: string }[] = [
  { code: "en", label: "English" },
  { code: "de", label: "German" },
  { code: "it", label: "Italian" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
];

export const DEFAULT_LANGUAGE_CODE = "en";

const KNOWN_CODES = new Set(LANGUAGES.map((l) => l.code));

/** Validates/normalizes a language code from user input or a header. Never
 * returns anything outside the curated list — unknown/missing input falls
 * back to English. */
export function resolveLanguageCode(input: string | null | undefined): string {
  const normalized = (input ?? "").trim().toLowerCase();
  return KNOWN_CODES.has(normalized) ? normalized : DEFAULT_LANGUAGE_CODE;
}

/** Best-effort initial guess from the browser's locale; always a curated
 * code, defaulting to English. Safe to call during render (no exceptions on
 * a missing/unusual `navigator`). */
export function detectBrowserLanguageCode(): string {
  if (typeof navigator === "undefined" || !navigator?.language) {
    return DEFAULT_LANGUAGE_CODE;
  }
  const primary = navigator.language.split("-")[0]?.toLowerCase() ?? "";
  return resolveLanguageCode(primary);
}
