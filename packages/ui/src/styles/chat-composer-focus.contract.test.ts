import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(path.join(__dirname, "chat-aui.css"), "utf8");

describe("composer focus", () => {
  it("keeps a visible keyboard ring on the live composer", () => {
    expect(css).not.toMatch(/aui-composer-input:focus-visible[^}]*outline:\s*none/);
    expect(css).toMatch(
      /\[data-thread-skin="digichat"\] \.aui-composer-input:focus-visible \{[^}]*outline: 1px solid var\(--accent\)/,
    );
  });
});
