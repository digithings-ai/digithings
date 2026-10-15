/**
 * Replace every mermaid code fence in a chapter with the image that names it
 * (DIG-2821).
 *
 * The rewrite belongs HERE, in the MDX pipeline, and not in a string rewrite
 * applied afterwards: the pages render the compiled MDX, so a rewrite that only
 * touched `Chapter.body` would put the diagram in `public/` and leave the
 * chapter showing a <code> block. That is exactly what the exported HTML
 * showed before this moved.
 *
 * The id is the same content hash `lib/book/diagram.ts` computes, duplicated
 * rather than imported because `next.config.mjs` cannot load a `.ts` file.
 * `remarkBookDiagrams.test.ts` pins the two against one another, so the copy
 * cannot drift silently: edit one, that test fails.
 */
import { createHash } from "node:crypto";

export const DIAGRAM_LANGS = ["mermaid", "mmd"];
const CR = /\r\n?/g;

/** Same canonical form as `normalizeDiagramSource` in ./diagram.ts. */
export function normalizeSource(source) {
  return source
    .replace(CR, "\n")
    .split("\n")
    .map((line) => line.replace(/[ \t]+$/, ""))
    .join("\n")
    .replace(/\n+$/, "");
}

/** Same id as `diagramId` in ./diagram.ts. */
export function diagramId(source) {
  return createHash("sha256").update(normalizeSource(source), "utf8").digest("hex").slice(0, 16);
}

export function diagramUrl(id) {
  return `/book/diagrams/${id}.svg`;
}

/**
 * @returns {(tree: object) => void} the mdast transformer.
 */
export default function remarkBookDiagrams() {
  return (tree) => {
    let index = 0;
    visit(tree);
    function visit(node) {
      if (!node || typeof node !== "object") return;
      if (node.type === "code" && DIAGRAM_LANGS.includes(String(node.lang ?? "").toLowerCase())) {
        // Mutated in place: mdast has no replace helper in the pipeline, and
        // swapping `node.type`/`node.url` keeps the parent's child list the same
        // length, which the tree walker relies on.
        node.type = "image";
        node.url = diagramUrl(diagramId(node.value));
        node.alt = `Figure ${index + 1}`;
        node.title = null;
        delete node.lang;
        delete node.meta;
        delete node.value;
        index += 1;
        return;
      }
      if (Array.isArray(node.children)) node.children.forEach(visit);
    }
  };
}
