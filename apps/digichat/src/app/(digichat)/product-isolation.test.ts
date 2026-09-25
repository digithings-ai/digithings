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
    expect(importLines).toMatch(/@digithings\/ui\/styles\/chat-core\.css/);
    expect(importLines).toMatch(/@digithings\/ui\/styles\/chat-aui\.css/);
    expect(importLines).toMatch(/@digithings\/ui\/styles\/chat-digichat\.css/);
    expect(importLines).toMatch(
      /@digithings\/ui\/styles\/digichat-app-theme\.css/,
    );
  });

  it("layout catalog templates own / instead of ChatShell", () => {
    const page = read("page.tsx");
    expect(page).toMatch(/skinOwnsPageChrome/);
    expect(page).toMatch(/HomeStockClient/);
  });

  it("uses stock Inter theme tokens like the baseline preview", () => {
    // Tokens live in the shared bridge globals.css imports (WS1).
    const bridge = read(
      "../../../../../packages/ui/src/styles/digichat-app-theme.css",
    );
    expect(bridge).toMatch(/--font-sans:\s*var\(--font-inter\)/);
    expect(bridge).toMatch(/--font-mono:\s*var\(--font-ibm-plex-mono\)/);
    expect(bridge).toMatch(/--background:\s*oklch\(1 0 0\)/);
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

  it("leaves thread footer spacing to the skin", () => {
    // Footer bottom air is single-sourced in the gallery Thread (pb-4
    // md:pb-6). A host padding override here would silently fork the footer
    // position per surface — catalog, product, and embed must share it.
    // (Background-only rules like the wide-transparent strip are fine.)
    const chrome = read("../../styles/product-chrome.css");
    expect(chrome).not.toMatch(/\.aui-thread-viewport-footer[^}]*padding/);
  });

  it("first-party digichat skin defaults to the expanded composer", () => {
    const skin = read("../../../../../packages/ui/src/components/chat/skins/digichat.tsx");
    expect(skin).toMatch(
      /composerLayout=\{composerLayout \?\? "expanded"\}/
    );
  });
});
