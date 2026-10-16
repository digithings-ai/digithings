/**
 * SSR tests for <Figure> (D1, #4429) — the `Fig N` numbered figure.
 *
 * The caption is the whole point of the part, so it is what is pinned: the
 * `Fig <n>` accent label, the em-dash separator, the caption text, and that the
 * content renders as the figure body. `n` accepts a string label as well as a
 * number.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Figure } from "./Figure";

describe("Figure — server render", () => {
  it("renders the Fig N label, separator and caption around the content", () => {
    const html = renderToStaticMarkup(
      <Figure n={1} caption="nine modules shipping">
        <div>metric</div>
      </Figure>,
    );

    expect(html).toContain("<figure");
    expect(html).toContain("<figcaption");
    expect(html).toContain("Fig 1");
    expect(html).toContain("nine modules shipping");
    expect(html).toContain(">metric<");
    // Caption label is the accent tone; the caption body is the muted ink.
    expect(html).toContain("text-accent");
    expect(html).toContain("text-ink-mute");
  });

  it("accepts a string label (sub-figures like 3a)", () => {
    const html = renderToStaticMarkup(
      <Figure n="3a" caption="detail">
        <span>x</span>
      </Figure>,
    );
    expect(html).toContain("Fig 3a");
  });

  it("appends a caller className", () => {
    const html = renderToStaticMarkup(
      <Figure n={2} caption="c" className="mt-[2rem]">
        <span>x</span>
      </Figure>,
    );
    expect(html).toContain("mt-[2rem]");
  });
});
