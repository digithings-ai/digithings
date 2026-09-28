/**
 * SSR tests for <Kbd/> — the keycap chip promoted from the reference's
 * reference-only global `.kbd` class. The point of the promotion is that the
 * keycap look is expressible in the kit's token utilities; these assertions
 * name those tokens directly, so a regression to a bespoke class family (or a
 * raw palette utility) fails here alongside the canon guard.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Kbd } from "./kbd";

describe("Kbd — keycap chip", () => {
  it("renders a semantic <kbd> with the keycap dress", () => {
    const html = renderToStaticMarkup(<Kbd>⌘</Kbd>);
    expect(html).toContain("<kbd");
    expect(html).toContain("⌘");
    expect(html).toContain("border-hair");
    expect(html).toContain("border-b-2");
    expect(html).toContain("bg-ink/5");
    expect(html).toContain("text-ink-soft");
    expect(html).toContain("font-mono");
  });

  it("carries a multi-character phase id without collapsing", () => {
    const html = renderToStaticMarkup(<Kbd>h7e</Kbd>);
    expect(html).toContain("h7e");
    expect(html).toContain("min-w-[1.15rem]");
  });

  it("merges a caller className and forwards anchor attributes", () => {
    const html = renderToStaticMarkup(
      <Kbd className="text-accent" title="phase-folder name">
        h9
      </Kbd>,
    );
    expect(html).toContain("text-accent");
    expect(html).toContain('title="phase-folder name"');
  });
});
