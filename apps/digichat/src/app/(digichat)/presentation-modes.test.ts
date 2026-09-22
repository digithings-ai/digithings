/**
 * `chrome.mode: modal | sidebar` are real presentation surfaces (#4515).
 *
 * They used to be folded into the `/embed` redirect, so a deployment that asked
 * for a pop-up or a docked panel got the bare iframe instead. These are source
 * guards: the mode has to reach the shell, and only `embed` may bounce out.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
/** `src/` — this test lives in `src/app/(digichat)/`. */
const srcDir = join(here, "..", "..");

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("chrome.mode presentation surfaces", () => {
  it("only redirects embed away from /", () => {
    const page = read("page.tsx");

    expect(page).toMatch(/if \(!layoutSkin && mode === "embed"\)/);
    expect(page).not.toMatch(/mode === "modal" \|\| mode === "sidebar"\)\s*\{\s*redirect/);
    // modal/sidebar mount the stock shell, so ChatShell must not claim them.
    expect(page).toMatch(/const framed = mode === "modal" \|\| mode === "sidebar"/);
    expect(page).toMatch(/client\.persistence === "server" && !framed/);
  });

  it("passes the real mode into the shell and frames the panel modes", () => {
    const client = read("home-stock-client.tsx");

    expect(client).toMatch(/import \{ PresentationFrame \}/);
    expect(client).toMatch(/const mode = clientConfig\.chrome\.mode/);
    expect(client).toMatch(/data-chrome-mode=\{mode\}/);
    expect(client).not.toMatch(/data-chrome-mode="app"/);
    // The launcher body is already viewport height; `h-dvh` there overflows it.
    expect(client).toMatch(/mode === "modal" \? "flex h-full flex-col"/);
    expect(client).toMatch(/<PresentationFrame mode=\{mode\} clientConfig=\{clientConfig\}>/);
  });

  it("mounts the launcher for modal and a docked panel for sidebar", () => {
    const frame = readFileSync(
      join(srcDir, "components", "stock", "presentation-frame.tsx"),
      "utf8",
    );

    expect(frame).toMatch(/import \{ DigichatLauncher \} from "@digithings\/ui\/chat\/launcher"/);
    expect(frame).toMatch(/hotkey=\{chrome\.launcher\?\.hotkey\}/);
    expect(frame).toMatch(/mode === "modal"/);
    expect(frame).toMatch(/mode === "sidebar"/);
    expect(frame).toMatch(/digichat-presentation__panel/);
  });

  it("styles the docked sidebar panel", () => {
    const css = readFileSync(join(srcDir, "styles", "product-chrome.css"), "utf8");

    expect(css).toMatch(/\.digichat-presentation--sidebar \{/);
    expect(css).toMatch(/\.digichat-presentation__canvas \{/);
    expect(css).toMatch(/\.digichat-presentation__panel \{/);
  });
});
