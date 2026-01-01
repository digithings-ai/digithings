/**
 * SSR test for <WordReveal> -- guards the hydration-mismatch fix (#2244).
 *
 * useMotionSafe() reports motion-safe unconditionally on the server (there is
 * no matchMedia to consult), so the SSR pass must always take the animated
 * words.map() branch, never the reduced-motion `text` branch or the
 * `is-static` class -- regardless of what the eventual client's real
 * preference turns out to be. If this ever renders the static branch during
 * SSR, the fix has regressed to reading a real (or `null`) `reduced` value
 * during render, reintroducing the mismatch.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MotionProvider } from "../../motion/primitives";
import { WordReveal } from "./WordReveal";

describe("WordReveal — server pass", () => {
  it("always takes the motion-safe branch during SSR", () => {
    const html = renderToStaticMarkup(
      <MotionProvider>
        <WordReveal text="You own the stack." />
      </MotionProvider>,
    );
    expect(html).not.toContain("is-static");
    expect(html).toContain('class="word"');
    expect(html).not.toContain(">You own the stack.<");
  });

  it("still carries the full claim in the aria-label for a no-JS/AT read", () => {
    const html = renderToStaticMarkup(
      <MotionProvider>
        <WordReveal text="You own the stack." />
      </MotionProvider>,
    );
    expect(html).toContain('aria-label="You own the stack."');
  });
});
