/**
 * Embed host wiring: stock Thread. Language / help chrome stays off.
 * Tool catalog is ProductStockShell-owned (sessionKey → X-Digi-Force-Tool).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const embedClientSrc = readFileSync(
  join(__dirname, "embed-client.tsx"),
  "utf8",
);

describe("embed stock chrome wiring", () => {
  it("mounts ProductStockShell (not CliThread)", () => {
    expect(embedClientSrc).toMatch(/ProductStockShell/);
    expect(embedClientSrc).not.toMatch(/CliThread/);
  });

  it("server page paints from the YAML install, not gated embed defaults", () => {
    const pageSrc = readFileSync(join(__dirname, "page.tsx"), "utf8");
    expect(pageSrc).toMatch(/resolveEmbedClientConfigForPaint/);
    expect(pageSrc).not.toMatch(/resolveEmbedClientConfigFromParams/);
  });

  it("does not mount language / help / new-conversation chrome", () => {
    expect(embedClientSrc).not.toMatch(/StockChromeBar/);
    expect(embedClientSrc).not.toMatch(/LanguageSelect/);
  });

  it("omits the in-iframe brand header on the digichat skin", () => {
    expect(embedClientSrc).toMatch(/shouldRenderEmbedBrandHeader/);
  });

  it("passes embed host sessionKey so ProductStockShell can arm force-tool", () => {
    expect(embedClientSrc).not.toMatch(/ToolCatalogBar/);
    expect(embedClientSrc).toMatch(/sessionKey=\{gate\.host\}/);
    expect(embedClientSrc).toMatch(/webSearchScope=\{webSearchScope\}/);
  });

  it("hides the in-iframe brand header on the first-party digichat skin (#3733)", () => {
    expect(embedClientSrc).toMatch(/shouldRenderEmbedBrandHeader/);
    expect(embedClientSrc).toMatch(/EmbedChatPrefsProvider/);
    expect(embedClientSrc).toMatch(/EmbedComposerMenu/);
    expect(embedClientSrc).toMatch(/setComposerMenu\("provider"\)/);
    expect(embedClientSrc).toMatch(/setComposerMenu\("mcp"\)/);
    expect(embedClientSrc).toMatch(/setComposerMenu\("tools"\)/);
    expect(embedClientSrc).not.toMatch(/aria-label="BYOK settings"/);
    expect(embedClientSrc).not.toMatch(/Page context from this host is attached/);
  });
});
