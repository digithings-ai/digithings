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
    const lead = read("work-status-lead.tsx");
    expect(lead).toMatch(/className="!size-3 shrink-0"/);
    const chain = read("gallery-thread/work-chain.tsx");
    const thread = read("gallery-thread/thread.aui.tsx");
    expect(chain).toContain("WorkStatusLead");
    expect(thread).toContain("WorkStatusLead");
  });

  it("sizes every sender of the marker at 12px in the digichat skin", () => {
    const css = readStyle("chat-digichat.css");
    const block = css.match(
      /\[data-slot="aui_work-status-marker"\] \[data-slot="dot-matrix"\],[\s\S]*?\{([\s\S]*?)\}/,
    );
    expect(block?.[1]).toContain("width: 0.75rem");
    expect(block?.[1]).toContain("height: 0.75rem");
    const selectors = block?.[0] ?? "";
    expect(selectors).toContain('[data-slot="tool-fallback-trigger"] > [data-slot="dot-matrix"]');
    // The reasoning glyph sits inside its icon wrapper, not on the trigger:
    // a child combinator here would drop it to its 14px utility size.
    expect(selectors).toContain('[data-slot="reasoning-trigger"] [data-slot="dot-matrix"]');
    expect(selectors).not.toContain('[data-slot="reasoning-trigger"] > [data-slot="dot-matrix"]');
    expect(selectors).toContain('.aui-message-error-root [data-slot="dot-matrix"]');
  });

  it("gives the loader and the chain header one shared box", () => {
    const css = readStyle("chat-digichat.css");
    const row = css.match(
      /\[data-slot="aui_assistant-message-indicator"\]\.aui-work-status,\n[\s\S]*?\[data-slot="aui_work-chain-trigger"\]\.aui-work-status \{\n([\s\S]*?)\n\}/,
    );
    expect(row?.[1]).toContain("display: flex");
    expect(row?.[1]).toContain("align-items: center");
    expect(row?.[1]).toContain("gap: 0.45rem");
    expect(row?.[1]).toContain("font-size: 0.7rem");
    expect(row?.[1]).toContain("line-height: 1");
    expect(row?.[1]).toContain("color: var(--ink-mute)");
    expect(row?.[1]).toContain("padding: 0");
    expect(row?.[1]).toContain("margin: 0");
  });

  it("renders the boot-loader steps with the shared marker and text size", () => {
    const lab = read("boot-lab.tsx");
    const markers = lab.match(/<DotMatrix[\s\S]*?className="([^"]*)"/g) ?? [];
    expect(markers.length).toBeGreaterThan(0);
    // Every status glyph left in the boot chain is a 12px box. The disclosure
    // caret is DisclosureChevron (0.55rem), not another 12px marker.
    for (const marker of markers) expect(marker).toMatch(/!?size-3\b/);
    expect(lab).not.toContain("size-3.5");
    expect(lab).not.toMatch(/text-sm/);
  });

  it("puts the error row in the shared boxed notice (DIG-4459)", () => {
    const error = read("gallery-thread/message-error.aui.tsx");
    // ErrorPrimitive.Root carries the notice box; the marker is the shared
    // 12px one from ChatNoticeContent.
    expect(error).toMatch(/<ErrorPrimitive\.Root[\s\S]{0,80}chatNoticeRootProps\("error", "aui-message-error-root/);
    expect(error).toContain("<ChatNoticeContent");
    const notice = read("stock/chat-notice.tsx");
    expect(notice).toMatch(/aui-chat-notice-marker !size-3/);
    expect(notice).not.toMatch(/text-sm/);
  });

  it("pins the pre-response row so the work chain cannot push it down", () => {
    const css = readStyle("chat-digichat.css");
    // The chain's part comes before the indicator in the message stream and the
    // assistant content is a flex column with a gap, so the moment the chain
    // mounts the gap alone pushes the marker down — the visible jump at the
    // handoff. The row is pinned to the content's top edge and the content keeps
    // the row's height while the row is alone, so the chain grows underneath it
    // (#4459). Scoped to the digichat skin: the base skin renders the indicator
    // without the hasContent guard, so overlaying it there would hide a live
    // chain trigger.
    expect(css).toMatch(
      /\[data-thread-skin="digichat"\]\s*\[data-slot="aui_assistant-message-content"\]:has\(\s*> \[data-slot="aui_assistant-message-indicator"\]\s*\) \{[\s\S]*?position: relative;[\s\S]*?min-height: 0\.75rem;/,
    );
    expect(css).toMatch(
      /\[data-thread-skin="digichat"\]\s*\[data-slot="aui_assistant-message-content"\]\s*> \[data-slot="aui_assistant-message-indicator"\] \{[\s\S]*?position: absolute;[\s\S]*?inset-block-start: 0;/,
    );
    expect(css).not.toMatch(
      /:is\(\.aui-theme-stage, \[data-thread-skin="digichat"\]\)\s*\[data-slot="aui_assistant-message-content"\]:has\(/,
    );
  });
});
