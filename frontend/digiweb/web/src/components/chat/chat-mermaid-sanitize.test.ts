/**
 * `sanitizeMermaidLabels` — pure string transform, no DOM/mermaid needed. See
 * the client suite (chat-mermaid.client.test.tsx) for the mocked-mermaid
 * component behaviour this feeds into.
 */
import { describe, expect, it } from "vitest";

import { sanitizeMermaidLabels } from "./ChatMermaidBlock";

describe("sanitizeMermaidLabels", () => {
  it("quotes an unquoted [...] label containing parens", () => {
    const out = sanitizeMermaidLabels("flowchart TD\n C[List locations (Exchange, OneDrive, Blob)]");
    expect(out).toContain('C["List locations (Exchange, OneDrive, Blob)"]');
  });

  it("leaves labels with no unparseable characters untouched", () => {
    const line = "A[User / Trial signup] --> B[Provision tenant + API key]";
    expect(sanitizeMermaidLabels(`flowchart TD\n ${line}`)).toContain(line);
  });

  it("leaves an already-quoted label untouched", () => {
    const line = 'C["already (quoted)"]';
    expect(sanitizeMermaidLabels(`flowchart TD\n ${line}`)).toContain(line);
  });

  it("quotes braces and does not touch the diamond-shape syntax it resembles", () => {
    const out = sanitizeMermaidLabels("flowchart TD\n C[Config {retries}]");
    expect(out).toContain('C["Config {retries}"]');
  });

  it("fixes the real diagram observed failing in production", () => {
    const code = [
      "flowchart TD",
      " A[User / Trial signup] --> B[Provision tenant + API key]",
      " B --> C[List locations (Exchange, OneDrive, Blob)]",
      " C --> D[Discovery: list users / mailboxes /items]",
      " D --> E[Scope job (PATCH job with target users)]",
      " H --> I{Content type}",
      " I --> |Email| J[24h fragments (owner + day)]",
      " I --> |OneDrive| K[one blob per file]",
    ].join("\n");
    const out = sanitizeMermaidLabels(code);
    expect(out).toContain('C["List locations (Exchange, OneDrive, Blob)"]');
    expect(out).toContain('E["Scope job (PATCH job with target users)"]');
    expect(out).toContain('J["24h fragments (owner + day)"]');
    // Untouched: no parens/braces in the label, and the {Content type} decision
    // shape is not a [...] node at all.
    expect(out).toContain("H --> I{Content type}");
    expect(out).toContain("K[one blob per file]");
  });
});
