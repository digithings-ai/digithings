import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * One loading row (#4459).
 *
 * The chain header is the reference: a 12px DotMatrix (`!size-3`), a `text-xs`
 * label in `--ink-mute`, flush to the message's left edge, one gap between the
 * marker and the text. Every other "something is loading" row — the inline
 * status line, the error banner, the boot-loader steps — has to read the same
 * numbers, or a row appearing shifts the text beside it.
 */
const here = dirname(fileURLToPath(import.meta.url));
const stylesDir = join(here, "..", "..", "styles");

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

function readStyle(name: string): string {
  return readFileSync(join(stylesDir, name), "utf8");
}

describe("one loading row", () => {
  it("keeps the chain header's 12px marker as the reference", () => {
    const chain = read("gallery-thread/work-chain.tsx");
    expect(chain).toMatch(/<DotMatrix[\s\S]{0,200}className="!size-3 shrink-0"/);
  });

  it("sizes every sender of the marker at 12px in the digichat skin", () => {
    const css = readStyle("chat-digichat.css");
    const block = css.match(
      /\[data-slot="aui_assistant-message-indicator"\] \[data-slot="dot-matrix"\],[\s\S]*?\{([\s\S]*?)\}/,
    );
    expect(block?.[1]).toContain("width: 0.75rem");
    expect(block?.[1]).toContain("height: 0.75rem");
    // The same block names the rows that must share the marker box.
    const selectors = css.slice(0, css.indexOf("width: 0.75rem"));
    expect(selectors).toContain('[data-slot="tool-fallback-trigger"] [data-slot="dot-matrix"]');
    expect(selectors).toContain('.aui-message-error-root [data-slot="dot-matrix"]');
  });

  it("gives the inline status row the chain header's type and gap", () => {
    const css = readStyle("chat-digichat.css");
    const row = css.match(
      /\[data-slot="aui_assistant-message-indicator"\] \{\n([\s\S]*?)\n\}/,
    );
    expect(row?.[1]).toContain("gap: 0.45rem");
    expect(row?.[1]).toContain("font-size: 0.7rem");
    expect(row?.[1]).toContain("line-height: 1");
    expect(row?.[1]).toContain("color: var(--ink-mute)");
    expect(row?.[1]).toContain("padding: 0");
  });

  it("renders the boot-loader steps with the shared marker and text size", () => {
    const lab = read("boot-lab.tsx");
    const markers = lab.match(/<DotMatrix[\s\S]*?className="([^"]*)"/g) ?? [];
    expect(markers.length).toBeGreaterThan(0);
    // Every glyph in the boot chain is a 12px box — the loading marker, the
    // reasoning marker and the chevron all sit in the same column.
    for (const marker of markers) expect(marker).toMatch(/!?size-3\b/);
    expect(lab).not.toContain("size-3.5");
    expect(lab).not.toMatch(/text-sm/);
  });

  it("brings the error row onto the same row anatomy", () => {
    const error = read("gallery-thread/message-error.aui.tsx");
    expect(error).toMatch(/className="aui-message-error-root[^"]*text-xs leading-none/);
    expect(error).toMatch(/className="!size-3 shrink-0/);
    expect(error).not.toMatch(/text-sm/);
    expect(error).not.toMatch(/px-4 py-3/);
  });
});
