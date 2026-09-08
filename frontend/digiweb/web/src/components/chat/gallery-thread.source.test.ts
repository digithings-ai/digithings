import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("gallery Thread is the product digichat skin", () => {
  it("does not compose a parallel ChatMarkdown tree", () => {
    const adapter = read("DigichatThread.tsx");
    expect(adapter).toMatch(/gallery-thread\/thread\.aui/);
    expect(adapter).not.toMatch(/from ["']\.\/ChatMarkdown["']/);
    expect(adapter).not.toMatch(/from ["']\.\/ChatThinking["']/);
    expect(adapter).not.toMatch(/from ["']\.\/ChatToolCall["']/);
    expect(adapter).not.toMatch(/from ["']@digithings\/web["']/);
  });

  it("gallery Thread mounts registry slots and cube glyphs", () => {
    const thread = read("gallery-thread/thread.aui.tsx");
    expect(thread).toMatch(/ActionBarMorePrimitive/);
    expect(thread).toMatch(/ReasoningRoot/);
    expect(thread).toMatch(/ToolFallback/);
    expect(thread).toMatch(/MarkdownText/);
    expect(thread).toMatch(/state="send"/);
    expect(thread).toMatch(/state="copy"|CopyActionIcon/);
    expect(thread).toMatch(/state="user"/);
    expect(thread).not.toMatch(/from ["']lucide-react["']/);
  });

  it("web package exposes Thread on a chat subpath, not the main barrel", () => {
    const pkg = read("../../../package.json");
    const index = read("../../index.ts");
    expect(pkg).toMatch(/"\.\/chat\/thread"/);
    expect(pkg).toMatch(/"\.\/chat\/dot-matrix"/);
    expect(index).not.toMatch(/DigichatThread/);
    expect(index).not.toMatch(/gallery-thread/);
  });
});
