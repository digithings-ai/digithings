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
    expect(layout).not.toMatch(/Geist_Mono/);
    expect(css).not.toMatch(/@digithings\//);
    expect(css).not.toMatch(/assistant-ui-cli/);
    expect(css).not.toMatch(/chat-core/);
  });

  it("uses the official assistant-ui template theme tokens", () => {
    const css = read("baseline.css");
    expect(css).toMatch(/--background:\s*oklch\(1 0 0\)/);
    expect(css).toMatch(/--font-sans:\s*var\(--font-inter\)/);
  });

  it("mounts ThreadSkinView for the official assistant-ui templates", () => {
    const client = read("baseline/baseline-client.tsx");
    const thread = read("stock/thread.aui.tsx");
    expect(client).toMatch(/ThreadSkinView/);
    expect(client).toMatch(/@\/components\/assistant-ui\/skins/);
    expect(client).toMatch(/THREAD_SKINS/);
    expect(thread).toContain("How can I help you today?");
    expect(thread).toContain("aui-thread-root");
    expect(thread).not.toContain("ask digichat");
    expect(client).not.toMatch(/StockChromeBar|ToolCatalogBar|ProductStockShell/);
  });
});
