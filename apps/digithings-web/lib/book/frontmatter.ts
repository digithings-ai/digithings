/**
 * The book's chapter frontmatter reader (DIG-2821).
 *
 * Chapters are `.mdx` files under `content/book`, each opening with a `---`
 * fenced header. This parses that header without pulling a YAML dependency:
 * the book's own schema is three scalar keys plus an optional list, and a
 * full YAML engine would let an author write something this reader silently
 * ignores — which is the failure mode a hand parser is chosen to avoid.
 *
 * Pure and dependency-free on purpose: the same function runs in the vitest
 * lane (`environment: "node"`) and inside the Next build, so a chapter that
 * parses here parses there.
 *
 * Anything it does not understand is an error, never a silent default: a
 * chapter with a misspelled key would otherwise ship with a blank title and
 * an unroutable slug.
 */

/** The keys a chapter header may carry. Unknown keys are rejected. */
export const CHAPTER_FRONTMATTER_KEYS = ["title", "order", "summary", "draft"] as const;

export type ChapterFrontmatterKey = (typeof CHAPTER_FRONTMATTER_KEYS)[number];

export interface ChapterFrontmatter {
  title: string;
  /** Chapter order in the book. Ties break on slug, so the ToC never depends
   *  on filesystem enumeration order. */
  order: number;
  summary: string;
  /** `true` keeps a chapter out of the ToC, the nav and the printed book. */
  draft: boolean;
}

export class FrontmatterError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FrontmatterError";
  }
}

/** True when `source` opens with a `---` fence on its own line. */
export function hasFrontmatter(source: string): boolean {
  return source.startsWith("---\n") || source.startsWith("---\r\n");
}

/**
 * Split a chapter into its frontmatter fields and its body.
 *
 * The fence must be the first line; a `---` later in the file is a thematic
 * break and is left in the body.
 */
export function splitFrontmatter(source: string): { yaml: string; body: string } {
  if (!hasFrontmatter(source)) {
    throw new FrontmatterError("chapter does not open with a `---` frontmatter fence");
  }
  const lines = source.split("\n");
  // lines[0] is the opening `---`; find the closing one.
  let close = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trimEnd() === "---") {
      close = i;
      break;
    }
  }
  if (close === -1) {
    throw new FrontmatterError("frontmatter fence is never closed");
  }
  const yaml = lines.slice(1, close).join("\n");
  const body = lines.slice(close + 1).join("\n");
  return { yaml, body };
}

function unquote(raw: string): string {
  const t = raw.trim();
  if (t.length >= 2 && ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'")))) {
    return t.slice(1, -1);
  }
  return t;
}

/**
 * Parse a frontmatter block into `ChapterFrontmatter`.
 *
 * Supported forms, and nothing else:
 *   `title: Why the book exists`      → string (quotes optional)
 *   `order: 2`                       → number
 *   `draft: true`                    → boolean
 *   `summary: >-` + indented block   → folded, one-line joined with a space
 *
 * `order` is required: it is the book's spine, and a chapter that sorts by
 * filename is a book whose order changes when a file is renamed.
 */
export function parseFrontmatter(yaml: string, where: string): ChapterFrontmatter {
  const out: Partial<Record<ChapterFrontmatterKey, string | number | boolean>> = {};
  const lines = yaml.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "" || line.trimStart().startsWith("#")) {
      i += 1;
      continue;
    }
    const match = /^([A-Za-z][A-Za-z0-9_-]*)\s*:\s?(.*)$/.exec(line);
    if (!match) {
      throw new FrontmatterError(`${where}: line ${i + 1} of the frontmatter is not \`key: value\``);
    }
    const key = match[1];
    const rest = match[2];
    if (!(CHAPTER_FRONTMATTER_KEYS as readonly string[]).includes(key)) {
      throw new FrontmatterError(
        `${where}: unknown frontmatter key \`${key}\` (expected one of ${CHAPTER_FRONTMATTER_KEYS.join(", ")})`,
      );
    }
    if (rest === ">" || rest === ">-" || rest === "|" || rest === "|-") {
      // Block scalar: every following line that is indented belongs to it.
      const parts: string[] = [];
      i += 1;
      while (i < lines.length && (lines[i].startsWith(" ") || lines[i].startsWith("\t"))) {
        parts.push(lines[i].trim());
        i += 1;
      }
      out[key as ChapterFrontmatterKey] = parts.filter(Boolean).join(" ");
      continue;
    }
    if (rest === "") {
      throw new FrontmatterError(`${where}: \`${key}\` has no value`);
    }
    if (key === "order") {
      const n = Number(rest.trim());
      if (!Number.isFinite(n)) {
        throw new FrontmatterError(`${where}: \`order\` must be a number, got \`${rest.trim()}\``);
      }
      out.order = n;
    } else if (key === "draft") {
      if (rest.trim() !== "true" && rest.trim() !== "false") {
        throw new FrontmatterError(`${where}: \`draft\` must be true or false, got \`${rest.trim()}\``);
      }
      out.draft = rest.trim() === "true";
    } else {
      out[key as ChapterFrontmatterKey] = unquote(rest);
    }
    i += 1;
  }

  const missing = (["title", "order", "summary"] as const).filter((k) => out[k] === undefined);
  if (missing.length) {
    throw new FrontmatterError(`${where}: frontmatter is missing ${missing.join(", ")}`);
  }
  return {
    title: String(out.title),
    order: out.order as number,
    summary: String(out.summary),
    draft: out.draft === true,
  };
}