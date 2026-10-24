import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

describe("package chat-digichat.css owns the digichat grammar", () => {
  const css = readFileSync(join(here, "../../styles/chat-digichat.css"), "utf8");

  it("scopes grammar to the gallery stage and product digichat skin", () => {
    expect(css).toContain('[data-thread-skin="digichat"]');
    expect(css).toContain(":is(.aui-theme-stage, [data-thread-skin=\"digichat\"])");
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
    expect(css).not.toMatch(/^\.aui-action-bar-more-content/m);
    expect(css).not.toMatch(/^\.aui-attachment-preview-dialog-content \{/m);
    expect(css).toMatch(/html:has\(\[data-thread-skin="digichat"\]\)/);
  });

  it("themes the slash trigger popover and /settings pane for the product skin", () => {
    expect(css).toContain(".aui-composer-trigger-popover");
    expect(css).toContain("[data-embed-settings]");
    expect(css).toContain('html:has([data-thread-skin="digichat"])');
  });

  it("remaps --font-mono to Geist on the product skin only", () => {
    const aui = readFileSync(join(here, "../../styles/chat-aui.css"), "utf8");
    const skinBlock = aui.slice(aui.indexOf('[data-thread-skin="digichat"]'));
    expect(skinBlock).toMatch(
      /--font-mono:\s*var\(--font-geist-mono\),\s*ui-monospace,\s*monospace/,
    );
  });

  it("no longer reaches into the reference app tree (WS1)", () => {
    // The shim and the gallery original are deleted; the package owns the sheet.
    expect(existsSync(join(here, "../../styles/chatbot.css"))).toBe(false);
    expect(
      existsSync(
        join(
          here,
          "../../../../../apps/reference/app/(chatbot)/chatbot/chatbot.css",
        ),
      ),
    ).toBe(false);
    // Provenance notes may name the old home; no rule may load a file from it.
    expect(css).not.toMatch(/apps\/reference\/[^\s]*\.css/);
    expect(css).not.toMatch(/@import[^;]*apps\/reference/);
  });
});

describe("the isolated /chatbot graph carries the shared theme toggle", () => {
  const reference = join(here, "../../../../../apps/reference");
  const shell = readFileSync(
    join(reference, "app/(chatbot)/chatbot-shell.css"),
    "utf8",
  );
  const layout = readFileSync(join(reference, "app/(chatbot)/layout.tsx"), "utf8");

  it("mounts the kit provider and toggle, and no local copy is left", () => {
    expect(layout).toContain('from "@digithings/ui/theme-provider"');
    expect(layout).toContain("<ThemeToggle");
    expect(layout).not.toContain("ChatbotThemeToggle");
    expect(layout).not.toContain("chatbotThemeInitScript");
    expect(
      existsSync(join(reference, "components/chatbot/chatbot-theme.tsx")),
    ).toBe(false);
  });

  it("scans the two kit files the toggle renders, and only those", () => {
    // source(none) means an unlisted file's utilities are simply not emitted:
    // ThemeToggle is ThemeProvider's IconButton, so hover:bg-ink/6 and the
    // focus ring live in icon-button.tsx.
    expect(shell).toContain(
      '@source "../../../../packages/ui/src/components/ThemeProvider.tsx";',
    );
    expect(shell).toContain(
      '@source "../../../../packages/ui/src/ui/icon-button.tsx";',
    );
  });
});
