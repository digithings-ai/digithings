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
    // NOT .dc-mermaid: MermaidBlock moved to @digithings/ui's ChatMermaidBlock
    // (.chat-md-mermaid*), so asserting it here pinned dead CSS in place.
    expect(css).not.toContain(".dc-mermaid");
  });

  it("session chrome is zero-radius ink/paper (utilitarian-terminal v0.1)", () => {
    const session = readFileSync(join(root, "src/styles/session.css"), "utf8");
    const cursor = readFileSync(join(root, "src/styles/cursor.css"), "utf8");
    expect(session).not.toMatch(/border-radius:\s*(?:[1-9]|999)/);
    expect(cursor).not.toMatch(/border-radius:\s*999px/);
    // Zero radius is the rule for the whole chrome, so it is declared once for
    // every control rather than repeated inside each rule that happens to need
    // it. One declaration, and it must still cover the composer's loud control.
    expect(session.match(/border-radius:/g)).toHaveLength(1);
    const zeroRadius = session.slice(session.indexOf(".dc-code-inline"), session.indexOf("border-radius: 0"));
    for (const selector of [".dc-textarea", ".dc-edit-textarea", ".dc-send", ".dc-stop", ".dc-byok-input", ".dc-quota-banner"]) {
      expect(zeroRadius).toContain(selector);
    }
    expect(session).toMatch(/\.dc-send\s*\{[^}]*background:\s*var\(--ink\)/s);
    expect(session).toMatch(/\.dc-send\s*\{[^}]*color:\s*var\(--bg\)/s);
  });

  it("names tokens and roles that exist in the canon", () => {
    const session = readFileSync(join(root, "src/styles/session.css"), "utf8");
    const cursor = readFileSync(join(root, "src/styles/cursor.css"), "utf8");
    expect(`${session}${cursor}`).not.toContain("--bg-term");
    // `--down` is a market direction; the state red is `--danger`.
    expect(`${session}${cursor}`).not.toMatch(/var\(--down/);
    expect(`${session}${cursor}`).not.toContain("#e0654b");
  });

  it("leaves focus to the global outline instead of disabling it locally", () => {
    const session = readFileSync(join(root, "src/styles/session.css"), "utf8");
    expect(session).not.toMatch(/outline:\s*none/);
    // The composer's focus state is the canon outline, not a 1px wash and not
    // nothing: removing `outline: none` alone would fall back to the UA ring.
    expect(session).toMatch(
      /\.dc-textarea:focus-visible[^{]*\{[^}]*outline:\s*2px solid var\(--accent\)/s,
    );
    // Decorative all-caps is not chrome: headings keep their own case.
    expect(session).not.toMatch(/text-transform:\s*uppercase/);
  });

  it("ships one wordmark, not a hand-copied second one", () => {
    // The canonical wordmark lives in @digithings/ui (Wordmark /
    // TerminalWordmark). This package carried a `.dc-wordmark` copy with its own
    // accent suffix: no consumers, and it drifted from the canon grammar.
    const index = readFileSync(join(root, "src/index.ts"), "utf8");
    const cursor = readFileSync(join(root, "src/styles/cursor.css"), "utf8");
    expect(index).not.toContain("DigiChatWordmark");
    expect(cursor).not.toContain(".dc-wordmark");
  });

  it("print transcript hides chrome but keeps turn text + sources (#3510)", () => {
    const css = readFileSync(join(root, "src/styles/session.css"), "utf8");
    expect(css).toContain("@media print");
    const printBlock = css.slice(css.indexOf("@media print"));
    for (const selector of [
      ".dc-form",
      ".dc-slash",
      ".dc-msg-actions",
      ".dc-msg-copy",
      ".dc-stop",
      ".dc-activities",
      ".dc-quota-banner",
      ".dc-byok-flow",
      ".dc-intro-byok",
    ]) {
      expect(printBlock).toContain(selector);
    }
    // Turn text + Sources cards stay printable.
    expect(printBlock).not.toContain(".dc-source-cards");
  });
});
