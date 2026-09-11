import { existsSync, readFileSync } from "node:fs";
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
    expect(thread).toMatch(/welcomeBody/);
    expect(thread).toMatch(/onComposerSubmit/);
    expect(thread).toMatch(/ComposerTriggerPopover/);
    expect(thread).toMatch(/Unstable_TriggerPopoverRoot/);
    expect(thread).toMatch(/char="@"/);
    expect(thread).toMatch(/mention\?: ThreadMentionTrigger/);
    expect(thread).toMatch(/digichat-thread__viewport/);
    expect(thread).not.toMatch(/state="assistant"/);
    expect(thread).not.toMatch(/from ["']lucide-react["']/);
  });

  it("tools stay collapsed unless they require action", () => {
    const fallback = read("gallery-thread/tool-fallback.aui.tsx");
    expect(fallback).toMatch(/useState\(isRequiresAction\)/);
    expect(fallback).toMatch(/formatToolDuration\(ms\)/);
    expect(fallback).not.toMatch(/isSettled/);
    expect(fallback).not.toMatch(/wantOpen/);
    expect(fallback).toMatch(/toolName/);
    expect(fallback).not.toMatch(/tool\(\$\{/);
    expect(fallback).not.toMatch(/`tool\(/);
  });

  it("reasoning uses thought when done and expand caret", () => {
    const reasoning = read("gallery-thread/reasoning.tsx");
    expect(reasoning).toMatch(/state=\{active \? "thinking" : "thought"\}/);
    expect(reasoning).toMatch(/state="expand"/);
  });

  it("container still COPY gallery chatbot.css", () => {
    const root = join(here, "../../../../../../");
    const cf = readFileSync(join(root, "Dockerfile.digichat-cloudflare"), "utf8");
    const app = readFileSync(join(root, "cloudflare/digichat/Dockerfile"), "utf8");
    const copy = "cloudflare/digiweb/reference/app/(chatbot)/chatbot/chatbot.css";
    expect(cf).toContain(copy);
    expect(app).toContain(copy);
  });

  it("portaled More-menu CSS is gated so catalog skins keep their menus", () => {
    const gate =
      ':is(html:has(.aui-theme-stage), html:has([data-thread-skin="digichat"])) .aui-action-bar-more-content';
    const popoverGate =
      ':is(html:has(.aui-theme-stage), html:has([data-thread-skin="digichat"])) .aui-composer-trigger-popover';
    const chatbot = read(
      "../../../../reference/app/(chatbot)/chatbot/chatbot.css",
    );
    const aui = read("../../styles/chat-aui.css");
    expect(chatbot).toContain(gate);
    expect(aui).toContain(gate);
    expect(chatbot).toContain(popoverGate);
    expect(aui).toContain(popoverGate);
    expect(chatbot).not.toMatch(/^\.aui-action-bar-more-content \{/m);
    expect(aui).not.toMatch(/^\.aui-action-bar-more-content \{/m);
  });

  it("product tooltip matches /chatbot: no rotated-square arrow", () => {
    const product = read("gallery-thread/ui/tooltip.tsx");
    const reference = read("../../../../reference/components/ui/tooltip.tsx");
    expect(product).toContain('data-tooltip-arrow="none"');
    expect(product).not.toMatch(/TooltipPrimitive\.Arrow/);
    expect(reference).toContain('data-tooltip-arrow="none"');
    expect(reference).not.toMatch(/TooltipPrimitive\.Arrow/);
  });

  it("markdown lists keep markers inside padding so a scrollport cannot clip them", () => {
    const chatbot = read(
      "../../../../reference/app/(chatbot)/chatbot/chatbot.css",
    );
    const aui = read("../../styles/chat-aui.css");
    const thread = read("gallery-thread/thread.aui.tsx");
    const markdown = read("gallery-thread/markdown-text.tsx");
    expect(chatbot).toMatch(/\.aui-md-ol \{[\s\S]*padding-inline-start: 2rem/);
    expect(chatbot).toContain("list-style-position: outside");
    expect(aui).toContain(".digichat-thread .aui-md-ol");
    expect(aui).toContain("padding-inline-start: 2rem");
    expect(thread).toMatch(/overflow-x-hidden/);
    expect(thread).not.toMatch(/overflow-x-auto overflow-y-scroll/);
    expect(markdown).toMatch(/aui-md-ol[\s\S]*ps-8 list-outside list-decimal/);
    expect(markdown).toMatch(/aui-md-ul[\s\S]*ps-7 list-outside list-disc/);
  });

  it("portaled tooltip CSS hides descendant svg, not only a direct child", () => {
    const chatbot = read(
      "../../../../reference/app/(chatbot)/chatbot/chatbot.css",
    );
    const aui = read("../../styles/chat-aui.css");
    const hide =
      ':is(html:has(.aui-theme-stage), html:has([data-thread-skin="digichat"])) [data-slot="tooltip-content"] svg';
    expect(chatbot).toContain(hide);
    expect(aui).toContain(hide);
  });

  it("gallery /chatbot specimens import the product Thread subpath", () => {
    const specimen = read(
      "../../../../reference/components/chatbot/chatbot-thread-specimen.tsx",
    );
    const chrome = read(
      "../../../../reference/components/chatbot/chatbot-chrome-specimen.tsx",
    );
    expect(specimen).toMatch(/from ["']@digithings\/web\/chat\/thread["']/);
    expect(chrome).toMatch(/from ["']@digithings\/web\/chat\/thread["']/);
    expect(specimen).not.toMatch(/assistant-ui\/elements\/thread/);
    expect(chrome).not.toMatch(/assistant-ui\/elements\/thread/);
  });

  it("does not keep a second registry Thread under the reference app", () => {
    const fork = join(
      here,
      "../../../../reference/components/assistant-ui/elements/thread.aui.tsx",
    );
    expect(existsSync(fork)).toBe(false);
  });

  it("gallery DotMatrix re-exports the chat subpath, not the main barrel", () => {
    const reexport = read("../../../../reference/components/ui/dot-matrix.tsx");
    expect(reexport).toMatch(/from ["']@digithings\/web\/chat\/dot-matrix["']/);
    expect(reexport).not.toMatch(/from ["']@digithings\/web["']/);
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
