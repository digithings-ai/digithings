import { motionValue } from "motion/react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DeckCard } from "./DeckStack";

describe("DeckCard listitem element", () => {
  it("renders a div, not an article, for the listitem role", () => {
    // `article` + `role="listitem"` fails axe aria-allowed-role; the deck
    // root is role="list", so a plain div is the valid listitem element.
    const html = renderToStaticMarkup(<DeckCard>card body</DeckCard>);
    expect(html).toContain('role="listitem"');
    expect(html).toContain("deck-card");
    expect(html).not.toContain("<article");
  });

  it("renders a div for the animated branch DeckStack clones into cards", () => {
    const html = renderToStaticMarkup(
      <DeckCard index={0} total={2} animate={false} progress={motionValue(0)}>
        card body
      </DeckCard>,
    );
    expect(html).toContain('role="listitem"');
    expect(html).toContain("deck-card");
    expect(html).not.toContain("<article");
  });
});
