import { describe, expect, it } from "vitest";

import {
  describeDiagram,
  diagramFile,
  diagramId,
  diagramMarkdown,
  diagramUrl,
  findDiagramFences,
  normalizeDiagramSource,
} from "./diagram";

const FLOW = ["graph TD", "  A[Author] --> B[Build]"].join("\n");

describe("diagramId", () => {
  it("is stable for the same source across calls", () => {
    expect(diagramId(FLOW)).toBe(diagramId(FLOW));
    expect(diagramId(FLOW)).toMatch(/^[0-9a-f]{16}$/);
  });

  it("changes when the diagram changes, so a stale SVG cannot be served", () => {
    expect(diagramId(FLOW)).not.toBe(diagramId(FLOW.replace("Build", "Book")));
  });

  // Two files that render identically must not produce two SVGs; a per-file
  // name would republish the whole diagram set on every CRLF checkout.
  it("ignores line endings and trailing whitespace", () => {
    const crlf = FLOW.split("\n").map((l) => `${l}   `).join("\r\n");
    expect(diagramId(crlf)).toBe(diagramId(FLOW));
  });

  it("does NOT ignore indentation, because mermaid layout depends on it", () => {
    const indented = FLOW.replace("  A[Author]", "    A[Author]");
    expect(diagramId(indented)).not.toBe(diagramId(FLOW));
  });
});

describe("the one-address contract", () => {
  // This is the brief's "the same SVG used in PDF" requirement, asserted as an
  // identity: the URL a page renders and the file the build writes are the same
  // id under one prefix each. If either prefix were typed at a call site, this
  // pair would drift and the two outputs would load different files.
  it("derives the url and the write path from the same id", () => {
    const d = describeDiagram(FLOW);
    expect(d.url).toBe(diagramUrl(d.id));
    expect(d.file).toBe(diagramFile(d.id));
    expect(d.url).toBe(`/book/diagrams/${d.id}.svg`);
    expect(d.file).toBe(`book/diagrams/${d.id}.svg`);
  });

  it("renders a fence as an image pointing at that one url", () => {
    const d = describeDiagram(FLOW);
    const md = diagramMarkdown({ index: 0, source: FLOW }, "Build steps");
    expect(md).toBe(`![Build steps](${d.url})`);
    expect(md).toContain("/book/diagrams/");
    // No component, no client bundle, nothing that prints differently.
    expect(md.startsWith("<")).toBe(false);
  });

  it("falls back to a positional caption when the author wrote none", () => {
    expect(diagramMarkdown({ index: 2, source: FLOW })).toMatch(/^!\[diagram 3]\(.*\.svg\)$/);
  });
});

describe("normalizeDiagramSource", () => {
  it("drops trailing blank lines and trailing spaces but keeps the shape", () => {
    expect(normalizeDiagramSource("a  \nb\n\n\n")).toBe("a\nb");
  });
});

describe("findDiagramFences", () => {
  it("collects mermaid and mmd fences in document order", () => {
    const body = [
      "text",
      "```mermaid",
      "graph TD",
      "  A --> B",
      "```",
      "more",
      "```mmd",
      "graph LR",
      "  C --> D",
      "```",
    ].join("\n");
    const fences = findDiagramFences(body);
    expect(fences.map((f) => f.index)).toEqual([0, 1]);
    expect(fences[0].source).toBe("graph TD\n  A --> B");
    expect(fences[1].source).toBe("graph LR\n  C --> D");
  });

  it("does not claim a non-mermaid fence", () => {
    const body = ["```sh", "npm ci", "```", "```ts", "const x = 1", "```"].join("\n");
    expect(findDiagramFences(body)).toEqual([]);
  });

  it("does not close a mermaid fence on an inner run of backticks", () => {
    const body = ["````mermaid", "graph TD", "  A[`x`] --> B", "```", "````"].join("\n");
    const fences = findDiagramFences(body);
    expect(fences).toHaveLength(1);
    expect(fences[0].source).toContain("A[`x`] --> B");
  });

  // Silently dropping an unterminated fence would publish a chapter whose
  // diagram is simply missing.
  it("throws on an unterminated fence, naming the opening line", () => {
    expect(() => findDiagramFences("intro\n\n```mermaid\ngraph TD")).toThrow(/unterminated.*line 3/);
  });

  it("CONTROL: a body with no fence yields none, and one with two yields two", () => {
    expect(findDiagramFences("just prose\n")).toEqual([]);
    expect(findDiagramFences("```mermaid\na\n```\n```mermaid\nb\n```\n")).toHaveLength(2);
  });
});

