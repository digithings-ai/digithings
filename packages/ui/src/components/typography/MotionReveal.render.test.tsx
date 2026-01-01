/**
 * SSR test for <MotionReveal> -- guards the same hydration seam <WordReveal/>
 * is tested for (#2244).
 *
 * useMotionSafe() reports motion-safe unconditionally on the server, so the SSR
 * pass must always take the animated words.map() branch and never the plain
 * `text` branch, whatever the eventual client's real preference turns out to
 * be. If this ever renders the plain branch during SSR, the fix has regressed
 * to reading a real (or `null`) reduced value during render.
 *
 * It also pins the band-scale intent: no pinned track, no `.wr-track` /
 * `.wr-sticky` markup — a supporting claim must not add dead scroll.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MotionProvider } from "../../motion/primitives";
import { MotionReveal } from "./MotionReveal";

describe("MotionReveal — server pass", () => {
  it("always takes the motion-safe branch during SSR", () => {
    const html = renderToStaticMarkup(
      <MotionProvider>
        <MotionReveal text="We run our own stack." />
      </MotionProvider>,
    );
    expect(html).toContain('class="word"');
    expect(html).not.toContain(">We run our own stack.<");
  });

  it("adds no pinned track — the band keeps its natural height", () => {
    const html = renderToStaticMarkup(
      <MotionProvider>
        <MotionReveal text="We run our own stack." />
      </MotionProvider>,
    );
    expect(html).not.toContain("wr-track");
    expect(html).not.toContain("wr-sticky");
  });
});
