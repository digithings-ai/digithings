/**
 * DeepSeek models sometimes echo their own search-template instruction into
 * the visible answer ("Use the results below to formulate an answer to the
 * user question unless additional information is needed"), often twice in a
 * row. It is never content, so drop it from rendered markdown (DIG-1210).
 */
const PHRASE =
  "Use the results below to formulate an answer to the user question unless additional information is needed";

const esc = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
// Words joined by flexible whitespace, so line-wrapped copies still match.
const FULL = PHRASE.split(" ").map(esc).join("\\s+");
/** One or more back-to-back full copies, with or without separators. */
const REPEATED = new RegExp(`\\s*(?:${FULL}\\s*[.,;:]?\\s*)+`, "gi");

/** Drop a copy cut off mid-phrase at the very end (streaming or truncated). */
function stripTrailingPartial(text: string): string {
  const lower = text.toLowerCase();
  const at = lower.lastIndexOf("use the");
  if (at < 0) return text;
  const tail = lower.slice(at).replace(/\s+/g, " ").trimEnd();
  return PHRASE.toLowerCase().startsWith(tail) ? text.slice(0, at).trimEnd() : text;
}

export function stripModelBoilerplate(text: string): string {
  const out = text.replace(REPEATED, (_m, offset: number) => (offset === 0 ? "" : " "));
  return stripTrailingPartial(out).replace(/ {2,}/g, " ");
}

type TextNode = { type: string; value?: string; children?: TextNode[] };

function walk(node: TextNode): void {
  if (node.type === "text" && typeof node.value === "string") {
    node.value = stripModelBoilerplate(node.value);
  }
  for (const child of node.children ?? []) walk(child);
}

/** remark plugin: strip the boilerplate from every text node. */
export function remarkStripModelBoilerplate() {
  return (tree: TextNode) => walk(tree);
}
