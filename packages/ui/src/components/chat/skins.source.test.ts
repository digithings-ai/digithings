import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(join(here, rel), "utf8");

// WS4: the skin system lives in the package under src/components/chat/ so it
// inherits the existing host `@source .../packages/ui/src/components/chat`
// scan line for free (chat-widgets.css) — zero stylesheet/@source changes.
describe("skins land in the package under components/chat", () => {
  it("web package exposes skins and stock on chat subpaths, not the main barrel", () => {
    const pkg = read("../../../package.json");
    const index = read("../../index.ts");
    expect(pkg).toMatch(/"\.\/chat\/skins"/);
    expect(pkg).toMatch(/"\.\/chat\/stock"/);
    expect(index).not.toMatch(/skins/);
    expect(index).not.toMatch(/chat\/stock/);
  });

  it("skins registry and stock primitives exist at the landing zone", () => {
    // Step 2: registry + contract + support contexts. Step 4: ThreadSkinView
    // (skins/index.ts), the skin/stock trees, and the transcript serializers.
    expect(existsSync(join(here, "skins/thread-skins.ts"))).toBe(true);
    expect(existsSync(join(here, "skins/thread-skin-host-contract.ts"))).toBe(
      true,
    );
    expect(existsSync(join(here, "skins/digichat.tsx"))).toBe(true);
    expect(existsSync(join(here, "stock/skin-chrome.tsx"))).toBe(true);
    expect(existsSync(join(here, "stock/stock-send-gate.tsx"))).toBe(true);
    expect(existsSync(join(here, "stock/deploy-ui-context.tsx"))).toBe(true);
    expect(existsSync(join(here, "stock/thread.aui.tsx"))).toBe(true);
    expect(existsSync(join(here, "stock/message-error.aui.tsx"))).toBe(true);
    expect(existsSync(join(here, "stock/embed-chat-prefs.tsx"))).toBe(true);
    expect(existsSync(join(here, "stock/stock-chat-prefs-host.tsx"))).toBe(true);
    expect(existsSync(join(here, "transcript/index.ts"))).toBe(true);
  });

  it("web package exposes the thread and transcript deep paths", () => {
    const pkg = read("../../../package.json");
    expect(pkg).toMatch(/"\.\/chat\/stock\/thread"/);
    expect(pkg).toMatch(/"\.\/chat\/transcript"/);
  });

  it("package skins never reach back into the app tree", () => {
    const skins = read("skins/index.ts");
    expect(skins).not.toMatch(/@\/lib\//);
    expect(skins).not.toMatch(/@\/components\//);
    expect(skins).not.toMatch(/@\/app\//);
    expect(skins).not.toMatch(/apps\/digichat/);
  });

  it("moved skin and stock modules never import app code", () => {
    // `@/lib/utils` (cn) is allowed: the package `@/*` alias resolves it to
    // the byte-identical src/lib/utils.ts.
    const files = [
      "skins/digichat.tsx",
      "stock/thread.aui.tsx",
      "stock/stock-chat-prefs-host.tsx",
      "stock/embed-chat-prefs.tsx",
      "stock/message-error.aui.tsx",
      "stock/attachment.aui.tsx",
      "stock/tool-fallback.aui.tsx",
    ];
    for (const f of files) {
      const src = read(f);
      expect(
        src,
        f,
      ).not.toMatch(
        /from "@\/(components|app|lib\/(thread-skins|embed-|product-|pending-|baseline-))/,
      );
      expect(src, f).not.toMatch(/from "@digithings\/digichat-ui"/);
    }
  });
});
