/**
 * Escape characters that make a `JSON.stringify(...)` payload unsafe to inline
 * into a `<script>` body or a `dangerouslySetInnerHTML` string.
 *
 * The input is always `JSON.stringify` output, so `<` / `>` / U+2028 / U+2029 are
 * the transformations that matter: each one has a JSON-legal escape whose parsed
 * value is identical, and each one closes a hole in an inline-script context.
 *
 * `\` and `/` are deliberately NOT in the pattern. Backslashes produced by
 * `JSON.stringify` must survive verbatim — escaping them again would corrupt the
 * value — and `/` carries no meaning inside a JSON document.
 */
const UNSAFE_CHARS = /[<>\b\f\n\r\t\0\u2028\u2029]/g;

const CHAR_MAP: Record<string, string> = {
  "<": "\\u003C",
  ">": "\\u003E",
  "\b": "\\b",
  "\f": "\\f",
  "\n": "\\n",
  "\r": "\\r",
  "\t": "\\t",
  "\0": "\\u0000",
  "\u2028": "\\u2028",
  "\u2029": "\\u2029",
};

export function escapeUnsafeChars(value: string): string {
  return value.replace(UNSAFE_CHARS, (char) => CHAR_MAP[char] ?? char);
}
