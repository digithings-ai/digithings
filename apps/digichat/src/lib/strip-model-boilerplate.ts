/**
 * DeepSeek models sometimes echo their own search-template instruction into
 * the visible answer ("Use the results below to formulate an answer to the
 * user question unless additional information is needed"), often twice in a
 * row. It is never content, so drop it from rendered markdown (DIG-1210).
 */
const BOILERPLATE =
  /\s*Use the results below to formulate an answer to the user question unless additional information is needed\.?/gi;

export function stripModelBoilerplate(text: string): string {
  return text.replace(BOILERPLATE, "");
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
