/**
 * Give every heading in a compiled chapter the id the table of contents links
 * to (DIG-2821).
 *
 * A rehype plugin rather than a React component for the headings: the id has
 * to be present in the STATIC HTML, because the printed book's table of
 * contents resolves a page number by looking the anchor up in the paginated
 * DOM. An id added during hydration is not in the HTML Playwright prints.
 *
 * The slug rules are duplicated from `headings.ts` on purpose — this file has
 * to be loadable by `next.config.mjs` without a TypeScript toolchain in the
 * config loader. `rehypeBookIds.test.ts` pins the two against the same corpus,
 * so the duplication cannot drift silently. Edit one, the test fails.
 */


/** Same alphabet as `slugify` in ./headings.ts. */
export function slugifyHeading(text) {
  const folded = text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  const slug = folded.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return slug === "" ? "section" : slug;
}

/** Plain text of a hast text node run. */
function textOf(node) {
  if (typeof node.value === "string") return node.value;
  if (!Array.isArray(node.children)) return "";
  return node.children.map(textOf).join("");
}

/**
 * @param {{}} _options  unused; the plugin takes no options on purpose, so a
 *                        caller cannot configure the ids away from the table of
 *                        contents that reads them.
 * @returns {(tree: object) => void} the transformer, which is the rehype shape.
 */
export default function rehypeBookIds() {
  return (tree) => {
    const seen = new Map();
    walk(tree, seen);
  };
}

function walk(node, seen) {
  if (!node || typeof node !== "object") return;
  if (node.type === "element" && node.tagName === "h1") {
    // The chapter title is the page's <h1>; it keeps its own id so the rail's
    // chapter link and the page agree.
    applyId(node, seen, 1);
  }
  if (node.type === "element" && /^h[1-6]$/.test(node.tagName ?? "")) {
    applyId(node, seen, Number(node.tagName.slice(1)));
  }
  if (Array.isArray(node.children)) node.children.forEach((child) => walk(child, seen));
}

function applyId(heading, seen, level) {
  const props = heading.properties ?? (heading.properties = {});
  const text = textOf(heading).trim();
  const base = slugifyHeading(text.replace(/[*_`~]/g, ""));
  const count = (seen.get(base) ?? 0) + 1;
  seen.set(base, count);
  props.id = count === 1 ? base : `${base}-${count}`;
  heading.data = { ...(heading.data ?? {}), level, text };
  return heading;
}
