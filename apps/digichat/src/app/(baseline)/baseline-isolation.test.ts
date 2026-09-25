import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("baseline preview isolation", () => {
  it("does not import digichat globals, tokens, or CLI skin", () => {
    const layout = read("layout.tsx");
    const css = read("baseline.css");
    expect(layout).not.toMatch(/import ["'].*globals\.css["']/);
    expect(layout).not.toMatch(/themeInitScript/);
    expect(layout).not.toMatch(/accent-digichat/);
    // The catalog renders the first-party `digichat` skin, whose theme reads
    // `--font-geist-mono`; only that font variable is borrowed from the app
    // shell — never its `data-theme` wiring.
    expect(layout).toMatch(/variable:\s*"--font-geist-mono"/);
    expect(layout).not.toMatch(/data-theme/);
    // The shared theme bridge is the only package import allowed here —
    // it carries the stock shadcn tokens both entry sheets used to duplicate.
    const bridge = "@digithings/ui/styles/digichat-app-theme.css";
    expect(css).toContain(bridge);
    const rest = css
      .split("\n")
      .filter((l) => !l.includes(bridge))
      .join("\n");
    expect(rest).not.toMatch(/@digithings\//);
    expect(css).not.toMatch(/assistant-ui-cli/);
    expect(css).not.toMatch(/chat-core/);
  });

  it("leaves thread footer geometry to the skin", () => {
    // Footer bottom air is single-sourced in the gallery Thread (pb-4
    // md:pb-6). A host override here would silently fork the footer position
    // per surface — catalog, product, and embed must share it.
    const css = read("baseline.css");
    expect(css).not.toMatch(/aui-thread-viewport-footer/);
  });

  it("uses the official assistant-ui template theme tokens", () => {
    // Tokens live in the shared bridge now; baseline.css only imports it.
    const bridge = read(
      "../../../../../packages/ui/src/styles/digichat-app-theme.css",
    );
    expect(bridge).toMatch(/--background:\s*oklch\(1 0 0\)/);
    expect(bridge).toMatch(/--font-sans:\s*var\(--font-inter\)/);
  });

  it("mounts ThreadSkinView for the official assistant-ui templates", () => {
    const client = read("baseline/baseline-client.tsx");
    const thread = read("../../../../../packages/ui/src/components/chat/stock/thread.aui.tsx");
    expect(client).toMatch(/ThreadSkinView/);
    expect(client).toMatch(/@digithings\/ui\/chat\/skins/);
    expect(client).toMatch(/THREAD_SKINS/);
    expect(thread).toContain("How can I help you today?");
    expect(thread).toContain("aui-thread-root");
    expect(thread).not.toContain("ask digichat");
    expect(client).not.toMatch(/StockChromeBar|ToolCatalogBar|ProductStockShell/);
  });
});
