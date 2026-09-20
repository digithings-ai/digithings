/**
 * SSR tests for the promoted prose atoms (D1, #4429).
 *
 * They pin the two things the promotion must preserve from the app-local copy:
 * (1) every atom is a plain server component that renders deterministically
 * with no DOM, and (2) the utility grammar is exactly the one that reproduces
 * the legacy `.section`/`.wrap`/`.kicker`/`.hero-title` look — if a value drifts
 * the pages shift silently, so the load-bearing utilities are asserted.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Mono, PageHead, RuledList, RuledRow } from "./prose";

describe("prose atoms — server render", () => {
  it("PageHead renders the kicker, display title and lede with the site grammar", () => {
    const html = renderToStaticMarkup(
      <PageHead
        kicker="// about"
        title={
          <>
            Infra<em>, not a product.</em>
          </>
        }
      >
        Body copy.
      </PageHead>,
    );

    expect(html).toContain("// about");
    expect(html).toContain("Body copy.");
    // Kicker: mono accent micro-label.
    expect(html).toContain("font-mono");
    expect(html).toContain("text-accent");
    // Title: the display face + the em accent the grammar carries.
    expect(html).toContain("font-display");
    // Rendered HTML escapes the arbitrary-variant `&` to `&amp;`.
    expect(html).toContain("_em]:text-accent");
    expect(html).toContain("<em>");
  });

  it("RuledList/RuledRow render a marker-free list with hairline rows and a mono term", () => {
    const html = renderToStaticMarkup(
      <RuledList>
        <RuledRow term="LangGraph">supervisor + sub-graph orchestration</RuledRow>
      </RuledList>,
    );

    expect(html).toContain("<ul");
    expect(html).toContain("list-none");
    expect(html).toContain("border-t border-hair");
    expect(html).toContain("last:border-b");
    expect(html).toContain("LangGraph");
    expect(html).toContain("supervisor + sub-graph orchestration");
  });

  it("Mono is inline code on the mono face", () => {
    const html = renderToStaticMarkup(<Mono>X-Request-ID</Mono>);
    expect(html).toContain("<code");
    expect(html).toContain("X-Request-ID");
    expect(html).toContain("font-mono");
  });
});
