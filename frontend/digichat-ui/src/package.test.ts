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

  it("session chrome is zero-radius ink/paper (utilitarian-terminal v0.1)", () => {
    const session = readFileSync(join(root, "src/styles/session.css"), "utf8");
    const cursor = readFileSync(join(root, "src/styles/cursor.css"), "utf8");
    expect(session).not.toMatch(/border-radius:\s*(?:[1-9]|999)/);
    expect(cursor).not.toMatch(/border-radius:\s*999px/);
    expect(session).toMatch(/\.dc-send\s*\{[^}]*border-radius:\s*0/s);
    expect(session).toMatch(/\.dc-send\s*\{[^}]*background:\s*var\(--ink\)/s);
    expect(session).toMatch(/\.dc-send\s*\{[^}]*color:\s*var\(--bg\)/s);
  });
});
