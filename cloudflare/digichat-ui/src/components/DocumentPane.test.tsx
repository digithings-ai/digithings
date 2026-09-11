import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { DocumentPane } from "./DocumentPane";

describe("DocumentPane", () => {
  it("renders vault markdown from body and never invents a URL from the path", () => {
    const html = renderToStaticMarkup(
      <DocumentPane
        hit={{
          title: "Auth plane",
          path: "clients/digithings/auth__p001",
          body: "# Auth\n\nRS256 tokens.",
        }}
        onClose={() => {}}
      />,
    );
    expect(html).toContain("Auth plane");
    expect(html).toContain("clients/digithings/auth__p001");
    expect(html).toContain("RS256 tokens");
    expect(html).not.toMatch(/href="clients\//);
    expect(html).not.toContain("http://");
    expect(html).not.toContain("https://");
  });

  it("offers Download only for a real http(s) URL", () => {
    const html = renderToStaticMarkup(
      <DocumentPane
        hit={{
          title: "Spec",
          path: "https://example.invalid/spec.pdf",
        }}
        onClose={() => {}}
      />,
    );
    expect(html).toContain("Download");
    expect(html).toContain('href="https://example.invalid/spec.pdf"');
    expect(html).toContain("application/pdf");
  });

  it("does not treat a vault path ending in .pdf as a downloadable URL", () => {
    const html = renderToStaticMarkup(
      <DocumentPane
        hit={{ title: "Scan", path: "clients/x/scan.pdf", snippet: "a paper scan" }}
        onClose={() => {}}
      />,
    );
    expect(html).not.toContain("Download");
    expect(html).not.toContain("application/pdf");
    expect(html).toContain("a paper scan");
  });

  it("falls back to readableSnippet for a get_note-shaped hit without body", () => {
    // Live digigraph RagSourceItem shape before/without wire body: doc_id + snippet.
    // Locks the non-http path rule and makes a regression to excerpt-only visible
    // once MiniMarkdown+body is the happy path (#3419).
    const html = renderToStaticMarkup(
      <DocumentPane
        hit={{
          title: "Auth plane",
          path: "clients/digithings/auth__p001",
          snippet: "# Auth\n\n**RS256** tokens for digikey. See the JWKS docs.",
        }}
        onClose={() => {}}
      />,
    );
    expect(html).toContain("Auth plane");
    expect(html).toContain("clients/digithings/auth__p001");
    expect(html).toContain("RS256 tokens for digikey");
    expect(html).not.toContain("**");
    expect(html).not.toContain("# Auth");
    expect(html).not.toMatch(/href="clients\//);
    expect(html).not.toContain("http://");
    expect(html).not.toContain("https://");
  });
});
