import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The Worked chain reads one density set. `--trace-*` are aliases of the
 * `--density-*` tokens, and the stack rhythm comes from a parent flex `gap` on
 * the chain content and the assistant turn — never from sibling margins.
 */
const stylesDir = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "styles");

function readStyle(name: string): string {
  return readFileSync(join(stylesDir, name), "utf8");
}

describe("worked chain spacing tokens", () => {
  const aui = readStyle("chat-aui.css");
  const skin = readStyle("chat-digichat.css");

  it("defines the scale and the default semantic tokens on the thread", () => {
    const block = aui.match(/\.digichat-thread,\n\.digichat-launcher \{([\s\S]*?)\n\}/);
    const body = block?.[1] ?? "";
    expect(body).toContain("--trace-space-1: 0.125rem");
    expect(body).toContain("--trace-space-2: 0.25rem");
    expect(body).toContain("--trace-space-3: 0.375rem");
    expect(body).toContain("--trace-space-4: 0.5rem");
    expect(body).toContain("--trace-space-5: 0.625rem");
    expect(body).toContain("--trace-space-6: 0.75rem");
    expect(body).toContain("--trace-space-7: 1rem");
    expect(body).toContain("--trace-space-8: 1.25rem");
    // The semantic names survive as aliases, so existing rules keep working.
    expect(body).toContain("--trace-title-gap: var(--density-gap-3)");
    expect(body).toContain("--trace-group-gap: var(--density-gap-2)");
    expect(body).toContain("--trace-within-gap: var(--density-gap-1)");
    expect(body).toContain("--trace-body-pad: var(--density-pad)");
    expect(body).toContain("--trace-chain-gap: var(--density-gap-4)");
  });

  it("puts the title gap and one sibling gap on the chain content", () => {
    expect(aui).toContain("gap: var(--trace-group-gap, 0.5rem)");
    expect(aui).toContain("padding-top: var(--trace-title-gap, 0.625rem)");
    expect(aui).not.toContain("padding-top: 0.3rem");
  });

  it("lays the chain content out as a column and hides it when folded", () => {
    const chain = aui.match(
      /\.digichat-thread \[data-slot="aui_work-chain-content"\],\n\.digichat-launcher \[data-slot="aui_work-chain-content"\] \{([\s\S]*?)\n\}/,
    );
    expect(chain?.[1] ?? "").toContain("display: flex");
    expect(chain?.[1] ?? "").toContain("flex-direction: column");
    // The flex display above would otherwise beat the UA `[hidden]` rule, so
    // both hosts (thread and launcher) need their own hidden rule.
    const hidden = aui.match(
      /\.digichat-thread \[data-slot="aui_work-chain-content"\]\[hidden\],\n\.digichat-launcher \[data-slot="aui_work-chain-content"\]\[hidden\] \{([\s\S]*?)\n\}/,
    );
    expect(hidden?.[1] ?? "").toContain("display: none");
  });

  it("keeps its scale out of the design tokens' --space-* names", () => {
    for (const sheet of [aui, skin]) {
      expect(sheet).not.toMatch(/(^|[^-a-z])--space-\d/m);
    }
  });

  it("zeroes the reasoning and tool-group margins once, in chat-aui.css", () => {
    expect(aui).toMatch(
      /\[data-slot="reasoning-root"\],[\s\S]*?\[data-slot="tool-group-root"\][\s\S]*?\{[^}]*margin: 0;/,
    );
    // The skin used to repeat the same two rules; the single source is aui.
    expect(skin).not.toMatch(/\[data-slot="reasoning-root"\]\s*\{/);
    expect(skin).not.toMatch(/\[data-slot="tool-group-root"\]\s*\{\s*margin: 0;/);
    expect(skin).not.toContain("margin-bottom: 1.25rem");
  });

  it("routes the reasoning body and the items inside a group through the tokens", () => {
    expect(skin).toContain("margin-top: var(--trace-header-gap, 0.25rem)");
    expect(skin).toContain("padding-block: var(--trace-body-pad, 0.125rem)");
    expect(skin).toContain("padding-inline: var(--trace-body-indent, 0.75rem) 0");
    expect(skin).toContain("margin-top: var(--density-gap-1, 0.25rem)");
    // The tool chain's item gap lives in aui, not twice in both sheets.
    expect(aui).toContain("gap: var(--density-gap-1, 0.125rem)");
    expect(skin).not.toContain("gap: var(--trace-within-gap, 0.25rem)");
    expect(skin).not.toContain("margin-top: 0.45rem");
    expect(skin).not.toContain("padding: 0.2rem 0 0.15rem 0.85rem");
    expect(skin).not.toContain("gap: 1rem");
  });

  it("spaces the assistant turn with one flex gap instead of sibling margins", () => {
    const content = skin.match(/\.aui-assistant-message-content \{\n([\s\S]*?)\n\}/);
    expect(content?.[1] ?? "").toContain("display: flex");
    expect(content?.[1] ?? "").toContain("flex-direction: column");
    expect(content?.[1] ?? "").toContain("gap: var(--density-gap-2, 0.5rem)");
    // The old doubles: sibling tool margins, chain margins and chain bottom.
    expect(aui).not.toContain('[data-slot="aui_tool-fallback"] + [data-slot="aui_tool-fallback"]');
    expect(aui).not.toMatch(/\[data-slot="aui_tool-chain"\][\s\S]{0,120}?margin-bottom/);
  });

  it("leaves no utility spacing on the reasoning and message stacks", () => {
    const components = join(stylesDir, "..", "components", "chat");
    const thread = readFileSync(join(components, "gallery-thread", "thread.aui.tsx"), "utf8");
    const reasoning = readFileSync(join(components, "gallery-thread", "reasoning.tsx"), "utf8");
    // The parent flex gap owns these; a `gap-y-*` or `space-y-*` here doubles it.
    expect(thread).not.toContain("mb-4 flex flex-col gap-y-6 empty:hidden");
    expect(reasoning).not.toContain("aui-reasoning-root mb-4");
    expect(reasoning).not.toContain("aui-reasoning-text-content space-y-4");
  });

  it("keeps the chain header's marker-to-label gap", () => {
    const row = skin.match(
      /\[data-slot="aui_assistant-message-indicator"\]\.aui-work-status,\n[\s\S]*?\[data-slot="aui_work-chain-trigger"\]\.aui-work-status \{\n([\s\S]*?)\n\}/,
    );
    expect(row?.[1]).toContain("gap: 0.45rem");
  });

  it("collapses an empty assistant footer so assistant -> user is the message gap", () => {
    const rule = skin.match(
      /\[data-slot="aui_assistant-message-footer"\]:not\(:has\(> \*\)\) \{([\s\S]*?)\}/,
    );
    expect(rule?.[1]).toContain("min-height: 0");
    expect(rule?.[1]).toContain("padding-top: 0");
    // The turn-to-turn gap is the density token, not a utility.
    expect(skin).toMatch(
      /\[data-slot="aui_message-group"\] \{\s*gap: var\(--density-gap-4/,
    );
  });
});
