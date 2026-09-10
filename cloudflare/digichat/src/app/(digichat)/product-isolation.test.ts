import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("product CSS isolation", () => {
  it("product layout/globals do not load CLI, session, or terminal sheets", () => {
    const layout = read("layout.tsx");
    const css = read("globals.css");

    expect(layout).toMatch(/Geist_Mono/);
    expect(layout).toMatch(/variable:\s*["']--font-geist-mono["']/);
    expect(layout).toMatch(/geistMono\.variable/);
    expect(layout).toMatch(/Inter/);
    expect(layout).toMatch(/IBM_Plex_Mono/);
    expect(layout).toMatch(/inter\.className/);
    expect(layout).not.toMatch(/geistMono\.className/);

    // Import lines only — comments may mention the forbidden sheets by name.
    const importLines = css
      .split("\n")
      .filter((l) => /^\s*@import\b/.test(l))
      .join("\n");

    expect(importLines).not.toMatch(/assistant-ui-cli/);
    expect(importLines).not.toMatch(/session\.css/);
    expect(importLines).not.toMatch(/cursor\.css/);
    expect(importLines).not.toMatch(/terminal-loaders/);
    expect(importLines).not.toMatch(/digichat-ui/);
    expect(importLines).toMatch(/product-chrome\.css/);
    expect(importLines).toMatch(/@digithings\/web\/styles\/chat-core\.css/);
    expect(importLines).toMatch(/@digithings\/web\/styles\/chat-aui\.css/);
    expect(importLines).toMatch(/@digithings\/web\/styles\/chatbot\.css/);
  });

  it("layout catalog templates own / instead of ChatShell", () => {
    const page = read("page.tsx");
    expect(page).toMatch(/skinOwnsPageChrome/);
    expect(page).toMatch(/HomeStockClient/);
  });

  it("uses stock Inter theme tokens like the baseline preview", () => {
    const css = read("globals.css");
    expect(css).toMatch(/--font-sans:\s*var\(--font-inter\)/);
    expect(css).toMatch(/--font-mono:\s*var\(--font-ibm-plex-mono\)/);
    expect(css).toMatch(/--background:\s*oklch\(1 0 0\)/);
  });

  it("ChatShell alone pulls the CLI sheet bundle", () => {
    const shell = read("../../components/chat-shell.tsx");
    const cli = read("../../styles/chat-shell-cli.css");
    expect(shell).toMatch(/chat-shell-cli\.css/);
    expect(cli).toMatch(/assistant-ui-cli\.css/);
    expect(cli).toMatch(/session\.css/);
    expect(cli).toMatch(/cursor\.css/);
    expect(cli).toMatch(/terminal-loaders/);
  });

  it("first-party digichat skin uses the compact composer off app chrome", () => {
    const skin = read("../../components/assistant-ui/skins/digichat.tsx");
    expect(skin).toMatch(
      /composerLayout=\{composerLayout \?\? \(mode === "app" \? "expanded" : "compact"\)\}/
    );
  });
});
