/**
 * SSR test for <Colophon>'s sweep -- guards the hydration-mismatch fix
 * (#2244), same mechanism as WordReveal.render.test.tsx: useMotionSafe()
 * reports motion-safe unconditionally on the server, so the SSR pass must
 * always apply the scroll-scrubbed backgroundPosition style, never fall
 * back to the reduced-motion `undefined` style -- regardless of the
 * eventual client's real preference.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MotionProvider } from "../motion/primitives";
import { Colophon, Footer } from "./chrome";

describe("Colophon — server pass", () => {
  it("always applies the sweep's motion style during SSR", () => {
    const html = renderToStaticMarkup(
      <MotionProvider>
        <Colophon name="digi" suffix="things" sweep />
      </MotionProvider>,
    );
    expect(html).toContain("colo-sweep");
    expect(html).toMatch(/class="colo-sweep" style="background-position:/);
  });

  it("omits the sweep span entirely when not opted in", () => {
    const html = renderToStaticMarkup(
      <MotionProvider>
        <Colophon name="digi" suffix="things" />
      </MotionProvider>,
    );
    expect(html).not.toContain("colo-sweep");
  });
});

describe("Footer profiles slot", () => {
  it("renders an optional profiles node next to the utility links", () => {
    const html = renderToStaticMarkup(
      <Footer
        links={[{ label: "Docs", href: "/docs" }]}
        meta="© 2026 digithings"
        profiles={<span data-slot="profiles">row</span>}
      />,
    );
    expect(html).toContain('data-slot="profiles"');
    expect(html).toContain("Docs");
    expect(html).toContain("© 2026 digithings");
  });

  it("keeps the utility row when no profiles are passed", () => {
    const html = renderToStaticMarkup(
      <Footer links={[{ label: "Docs", href: "/docs" }]} meta="© 2026 digithings" />,
    );
    expect(html).toContain("Docs");
    expect(html).not.toContain("data-slot=\"profiles\"");
  });
});
