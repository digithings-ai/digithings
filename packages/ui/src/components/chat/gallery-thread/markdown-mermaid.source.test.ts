import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("gallery-thread markdown renders mermaid via the assistant-ui element", () => {
  it("wires mermaid fences through componentsByLanguage to MermaidDiagram", () => {
    const source = read("markdown-text.tsx");
    expect(source).toMatch(/componentsByLanguage=\{\{/);
    expect(source).toMatch(/mermaid:\s*\{\s*SyntaxHighlighter:\s*MermaidDiagram/);
    expect(source).toMatch(
      /from ["']\.\.\/\.\.\/assistant-ui\/elements\/mermaid-diagram\.aui["']/,
    );
  });

  it("no longer routes mermaid fences to the nested-source ChatMermaidBlock", () => {
    const source = read("markdown-text.tsx");
    expect(source).not.toMatch(/ChatMermaidBlock/);
  });
});
