/**
 * Embed host wiring: stock Thread only — no language / help / tool chrome.
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

  it("does not mount language / help / new-conversation / tool chrome", () => {
    expect(embedClientSrc).not.toMatch(/StockChromeBar/);
    expect(embedClientSrc).not.toMatch(/ToolCatalogBar/);
  });

  it("does not mount LanguageSelect dropdown", () => {
    expect(embedClientSrc).not.toMatch(/LanguageSelect/);
  });
});
