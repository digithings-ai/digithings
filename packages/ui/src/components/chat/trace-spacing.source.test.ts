import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The Worked chain reads one spacing scale. Default values are the fixed
 * rhythm: room under the title, one gap between sibling groups, a tighter
 * gap inside a group, and a short step from a header into its body.
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
    expect(body).toContain("--space-1: 0.125rem");
    expect(body).toContain("--space-2: 0.25rem");
    expect(body).toContain("--space-3: 0.375rem");
    expect(body).toContain("--space-4: 0.5rem");
    expect(body).toContain("--space-5: 0.625rem");
    expect(body).toContain("--space-6: 0.75rem");
    expect(body).toContain("--space-7: 1rem");
    expect(body).toContain("--trace-title-gap: var(--space-5)");
    expect(body).toContain("--trace-group-gap: var(--space-4)");
    expect(body).toContain("--trace-within-gap: var(--space-2)");
    expect(body).toContain("--trace-header-gap: var(--space-2)");
    expect(body).toContain("--trace-body-pad: var(--space-1)");
    expect(body).toContain("--trace-body-indent: var(--space-6)");
    expect(body).toContain("--trace-chain-gap: var(--space-6)");
  });

  it("puts the title gap and one sibling gap on the chain content", () => {
    expect(aui).toContain("gap: var(--trace-group-gap, 0.5rem)");
    expect(aui).toContain("padding-top: var(--trace-title-gap, 0.625rem)");
    expect(aui).not.toContain("padding-top: 0.3rem");
  });

  it("gives reasoning and tool groups the same sibling margin", () => {
    expect(aui).toMatch(
      /\[data-slot="reasoning-root"\],[\s\S]*?\[data-slot="tool-group-root"\][\s\S]*?\{[^}]*margin: 0;/,
    );
    expect(skin).toMatch(/\[data-slot="reasoning-root"\] \{\s*\/\*[\s\S]*?\*\/\s*margin: 0;\s*\}/);
    expect(skin).toMatch(/\[data-slot="tool-group-root"\] \{\s*margin: 0;\s*\}/);
    expect(skin).not.toContain("margin-bottom: 1.25rem");
  });

  it("routes the reasoning body and the items inside a group through the tokens", () => {
    expect(skin).toContain("margin-top: var(--trace-header-gap, 0.25rem)");
    expect(skin).toContain("padding-block: var(--trace-body-pad, 0.125rem)");
    expect(skin).toContain("padding-inline: var(--trace-body-indent, 0.75rem) 0");
    expect(skin).toContain("margin-top: var(--trace-within-gap, 0.25rem)");
    expect(skin).toContain("gap: var(--trace-within-gap, 0.25rem)");
    expect(skin).not.toContain("margin-top: 0.45rem");
    expect(skin).not.toContain("padding: 0.2rem 0 0.15rem 0.85rem");
    expect(skin).not.toContain("gap: 1rem");
  });

  it("keeps the chain header's marker-to-label gap", () => {
    const row = skin.match(
      /\[data-slot="aui_assistant-message-indicator"\]\.aui-work-status,\n[\s\S]*?\[data-slot="aui_work-chain-trigger"\]\.aui-work-status \{\n([\s\S]*?)\n\}/,
    );
    expect(row?.[1]).toContain("gap: 0.45rem");
  });
});
