import { describe, expect, it } from "vitest";

import remarkBookDiagrams, { diagramId, normalizeSource } from "./remarkBookDiagrams.mjs";
import { diagramId as referenceId, normalizeDiagramSource } from "./diagram.ts";
import { findDiagramFences } from "./diagram.ts";

/**
 * The plugin duplicates the hash from `lib/book/diagram.ts` because
 * `next.config.mjs` cannot load a `.ts` file. This is the pin: the build step
 * writes the SVG under the id this plugin links to, so if the two hashes ever
 * disagree the chapter shows a 404 — with nothing failing.
 */

const code = (lang: string, value: string) => ({ type: "code", lang, value, meta: null });
const para = (value: string) => ({ type: "paragraph", children: [{ type: "text", value }] });

const run = (children: object[]) => {
  const tree = { type: "root", children };
  remarkBookDiagrams()(tree as never);
  return children as Array<Record<string, unknown>>;
};

const SOURCES = [
  "graph TD\n  A[Author] --> B[Build]",
  "graph LR\n  C --> D",
  "graph TD  \n  A --> B   \n\n",
  "graph TD\r\n  A --> B",
];

describe("the plugin and the build step agree on every address", () => {
  it.each(SOURCES)("hashes %j the same as lib/book/diagram.ts", (source) => {
    expect(diagramId(source)).toBe(referenceId(source));
  });

  it("normalises the same way, line endings and trailing space included", () => {
    for (const source of SOURCES) expect(normalizeSource(source)).toBe(normalizeDiagramSource(source));
  });

  // The real end-to-end statement: what the build writes and what the page
  // asks for are the same string.
  it("links the file the build step renders", () => {
    const body = SOURCES.map((s, i) => "```mermaid\n" + s + "\n```").join("\n\n");
    const fences = findDiagramFences(body);
    const rewritten = run(fences.map((f) => code("mermaid", f.source)));
    for (const [i, node] of rewritten.entries()) {
      expect(node.url).toBe(`/book/diagrams/${fences[i].source ? diagramId(fences[i].source) : ""}.svg`);
    }
  });
});

describe("the rewrite", () => {
  it("turns a mermaid code node into an image carrying the hash", () => {
    const node = run([code("mermaid", "graph TD\n A --> B")])[0];
    expect(node.type).toBe("image");
    expect(node.url).toMatch(/^\/book\/diagrams\/[0-9a-f]{16}\.svg$/);
    expect(node.alt).toBe("Figure 1");
  });

  it("accepts mmd as well as mermaid", () => {
    expect(run([code("mmd", "graph LR\n C --> D")])[0].type).toBe("image");
  });

  it("leaves prose and every other language alone", () => {
    const children = [para("hello"), code("sh", "npm ci"), code("ts", "const x = 1")];
    const out = run(children);
    expect(out.map((n) => n.type)).toEqual(["paragraph", "code", "code"]);
    expect(out[1].value).toBe("npm ci");
  });

  it("numbers several diagrams in document order", () => {
    const out = run([code("mermaid", "graph TD\n A --> B"), code("mermaid", "graph LR\n C --> D")]);
    expect(out.map((n) => n.alt)).toEqual(["Figure 1", "Figure 2"]);
  });

  it("CONTROL: a chapter with no fence comes back untouched", () => {
    const children = [para("only prose")];
    run(children);
    expect(children[0].type).toBe("paragraph");
    expect(children[0].children).toEqual([{ type: "text", value: "only prose" }]);
  });
});
