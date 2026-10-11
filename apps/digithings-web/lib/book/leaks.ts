/**
 * The digibook editorial lint (DIG-2818 rule, 2026-10-11).
 *
 * digibook is high level: architecture, design decisions and the reasons for
 * them, how to use digithings and what can be built with it. Implementation
 * detail lives in the reference docs and is reached through `<Reference>`
 * cards. This catches the obvious leaks before a chapter ships:
 *
 *  - environment / secret variable names (`ALL_CAPS_WITH_UNDERSCORES`)
 *  - loopback hosts (`localhost`, `127.0.0.1`, `0.0.0.0`)
 *  - `host:port` / `:8000` style port numbers
 *  - secret-like words (api key, password, private key, bearer, client secret…)
 *
 * It is deliberately blunt. A line that must keep a match says why with a
 * trailing `{/* book-lint-allow: <reason> *\/}` comment, which is reviewable.
 * `<Reference href="…">` attribute values are exempt: a link target is where
 * the detail is SUPPOSED to live.
 */

export interface Leak {
  line: number;
  rule: "env-name" | "loopback" | "port" | "secret-word";
  match: string;
  text: string;
}

const RULES: Array<{ rule: Leak["rule"]; re: RegExp }> = [
  { rule: "env-name", re: /\b[A-Z][A-Z0-9]*_[A-Z0-9_]*[A-Z0-9]\b/g },
  { rule: "loopback", re: /\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0)\b/gi },
  { rule: "port", re: /(?:[A-Za-z0-9\])]|^|\s|`):\d{2,5}\b/g },
  {
    rule: "secret-word",
    re: /\b(?:api[ _-]?keys?|secret[ _-]?keys?|client[ _-]?secrets?|passwords?|private[ _-]?keys?|bearer|access[ _-]?tokens?|service[ _-]?role[ _-]?keys?)\b/gi,
  },
];

const ALLOW = /\{\/\*\s*book-lint-allow:[^*]+\*\/\}\s*$/;
const REFERENCE_HREF = /(<Reference\b[^>]*?\bhref=)"[^"]*"/g;
const MD_LINK_TARGET = /\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;

/** Every leak in a chapter source, frontmatter excluded. */
export function findLeaks(source: string): Leak[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  let start = 0;
  if (lines[0] === "---") {
    const end = lines.indexOf("---", 1);
    if (end > 0) start = end + 1;
  }
  const out: Leak[] = [];
  for (let i = start; i < lines.length; i++) {
    const raw = lines[i];
    if (ALLOW.test(raw)) continue;
    const text = raw.replace(REFERENCE_HREF, '$1""').replace(MD_LINK_TARGET, "]()");
    for (const { rule, re } of RULES) {
      re.lastIndex = 0;
      for (const m of text.matchAll(re)) out.push({ line: i + 1, rule, match: m[0].trim(), text: raw.trim() });
    }
  }
  return out;
}
