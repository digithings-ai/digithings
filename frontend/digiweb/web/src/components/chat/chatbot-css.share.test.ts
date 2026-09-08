import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

describe("gallery chatbot.css product share", () => {
  const css = readFileSync(
    join(here, "../../../../reference/app/(chatbot)/chatbot/chatbot.css"),
    "utf8",
  );
  const productImport = readFileSync(join(here, "../../styles/chatbot.css"), "utf8");

  it("scopes grammar to the gallery stage and product digichat skin", () => {
    expect(css).toContain('[data-thread-skin="digichat"]');
    expect(css).toContain(":is(.aui-theme-stage, [data-thread-skin=\"digichat\"])");
    expect(productImport).toMatch(/chatbot\/chatbot\.css/);
  });

  it("keeps the 72vh specimen frame on the gallery stage only", () => {
    expect(css).toMatch(
      /\.aui-theme-stage \{\s*height:\s*min\(72vh, 46rem\);/,
    );
    expect(css).not.toMatch(
      /:is\([^)]+\) \{\s*height:\s*min\(72vh, 46rem\)/,
    );
  });

  it("does not restyle catalog dialogs globally", () => {
    expect(css).not.toMatch(/^\s*\[data-slot="dialog-overlay"\]/m);
    expect(css).toMatch(/html:has\(\[data-thread-skin="digichat"\]\)/);
  });

  it("remaps --font-mono to Geist on the product skin only", () => {
    const aui = readFileSync(join(here, "../../styles/chat-aui.css"), "utf8");
    const skinBlock = aui.slice(aui.indexOf('[data-thread-skin="digichat"]'));
    expect(skinBlock).toMatch(
      /--font-mono:\s*var\(--font-geist-mono\),\s*ui-monospace,\s*monospace/,
    );
  });
});
