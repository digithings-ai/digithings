import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("@digithings/digichat-ui package surface", () => {
  it("exports session styles", () => {
    const css = readFileSync(join(root, "src/styles/session.css"), "utf8");
    expect(css).toContain(".dc-session");
    expect(css).toContain(".dc-thread");
    // NOT .dc-mermaid: MermaidBlock moved to @digithings/web's ChatMermaidBlock
    // (.chat-md-mermaid*), so asserting it here pinned dead CSS in place.
    expect(css).not.toContain(".dc-mermaid");
  });
});
