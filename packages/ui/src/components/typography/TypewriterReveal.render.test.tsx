/**
 * SSR test for <TypewriterReveal> — the same hydration seam its siblings are
 * tested for (#2244), plus the two contracts that make the typewriter usable at
 * all: the layout is held by a ghost, and the finished line is exposed once to
 * assistive tech.
 *
 * useMotionSafe() is false on the server, so the server pass renders the whole
 * line untyped and with no caret. That is the point: the HTML always contains a
 * complete quote, so there is nothing for the client's hydrated tree to disagree
 * with, and a reader with no JS gets the copy rather than an empty box.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MotionProvider } from "../../motion/primitives";
import { TypewriterReveal } from "./TypewriterReveal";

describe("TypewriterReveal — server pass", () => {
  const html = () =>
    renderToStaticMarkup(
      <MotionProvider>
        <TypewriterReveal text="The stack declines to bet on a provider." />
      </MotionProvider>,
    );

  it("renders the whole line during SSR, untyped and with no caret", () => {
    const out = html();
    expect(out).toContain("The stack declines to bet on a provider.");
    expect(out).not.toContain("tw-caret");
  });

  it("holds the layout with a ghost so the band never reflows", () => {
    const out = html();
    expect(out).toContain('class="tw-ghost"');
    expect(out).toContain('class="tw-live"');
  });

  it("exposes the finished line once, for a screen reader", () => {
    const out = html();
    expect(out).toContain('class="tw-sr"');
    /* Both visual layers are hidden from the accessibility tree. */
    expect(out.match(/aria-hidden="true"/g)).toHaveLength(2);
  });

  it("adds no pinned track — the band keeps its natural height", () => {
    const out = html();
    expect(out).not.toContain("wr-track");
    expect(out).not.toContain("wr-sticky");
  });
});
