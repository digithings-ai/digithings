import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const chat = path.resolve(__dirname, "..");
const read = (rel: string) => readFileSync(path.join(chat, rel), "utf8");

/** Every skin's assistant message has the "…" menu with Export ▸. */
const MORE_MENU_SKINS = [
  "skins/base/thread.tsx",
  "skins/chatgpt.tsx",
  "skins/claude.tsx",
  "skins/grok.tsx",
  "skins/gemini.tsx",
  "skins/perplexity.tsx",
  "stock/thread.aui.tsx",
  "gallery-thread/thread.aui.tsx",
];

/** Skins without the aui-* classes the HTML snapshot looks for. */
const CLONE_SKINS = [
  "skins/chatgpt.tsx",
  "skins/claude.tsx",
  "skins/grok.tsx",
  "skins/gemini.tsx",
  "skins/perplexity.tsx",
];

describe("chat export wiring", () => {
  it.each(MORE_MENU_SKINS)("%s uses the shared Export submenu", (rel) => {
    const src = read(rel);
    expect(src).toMatch(/<MessageExportMenu\b/);
    expect(src).not.toMatch(/ActionBarMorePrimitive\.Item/);
    expect(src).not.toMatch(/Export as HTML/);
  });

  it.each(CLONE_SKINS)("%s marks its thread, chrome and roles for the snapshot", (rel) => {
    const src = read(rel);
    expect(src).toMatch(/data-export-thread=""/);
    expect(src).toMatch(/<ComposerPrimitive\.Root[^>]*data-export-chrome=""/s);
    expect(src).toMatch(/data-role=/);
  });

  it("the palette runs /export through the shared runner, guarded in private mode", () => {
    const src = read("stock/skin-slash-palette.tsx");
    expect(src).toContain("exportConversation({");
    expect(src).toContain("bindThreadExport");
    expect(src).toMatch(/if \(privateMode\)/);
  });
});
