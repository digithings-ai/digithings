import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PipelineBand } from "@/app/_bands/pipeline";

describe("PipelineBand", () => {
  const html = renderToStaticMarkup(<PipelineBand />);

  it("names the section agent orchestration and stacks four workflow cards", () => {
    expect(html).toContain("Agent orchestration");
    expect(html).not.toContain("Four pipelines");
    expect(html).not.toContain("AI agentic workflow infrastructure");
    expect(html).toContain("deck-slots");
    expect(html).toContain("deck-card");
    expect(html.match(/class="deck-card/g)).toHaveLength(4);
    const headings = ["Research", "Investment portfolio", "Strategy building", "Trade setups"];
    let cursor = 0;
    for (const name of headings) {
      const at = html.indexOf(`>${name}<`, cursor);
      expect(at).toBeGreaterThanOrEqual(0);
      cursor = at;
    }
  });

  it("keeps the facts and does not finish the last two workflows", () => {
    expect(html).not.toContain("two done");
    expect(html).not.toContain("Still to come");
    expect(html).not.toContain("still to come");
    expect(html.match(/in development/g)).toHaveLength(2);
    expect(html).toContain("digiquant baseline research");
    expect(html).toContain("custom knowledge base");
    expect(html).not.toMatch(/12x|fx hub/i);
    expect(html).toContain("digithings");
    expect(html).toContain("digigraph");
    expect(html).toContain("digiquant baseline portfolio");
    expect(html).toContain("entry, a stop, and a target");
    expect(html).toContain("Monitoring");
    expect(html).toContain("Agent selects a level");
    expect(html).toContain("not a live run");
    expect(html).not.toMatch(/DigiQuant|DigiThings|DigiCon|Grokopedia/);
  });

  it("draws parallel steps and does not revive the downward runway", () => {
    expect(html).toContain("in parallel");
    expect(html).toContain("Web search");
    expect(html).toContain("Custom knowledge base");
    expect(html).toContain("Prices");
    expect(html).toContain("Charts");
    expect(html).not.toContain("100svh+220svh");
    expect(html).not.toContain("motion-safe:");
    expect(html).not.toContain("StageRunway");
  });

  /* DIG-2854: the head pins, so the deck must stop at the pinned rule. The
     two assertions below are one invariant, and either alone is satisfiable by
     the wrong thing — `band-pin` with the old --deck-top pins the head and
     then hides the top of every card under it; --band-pin-h with no pin moves
     the deck for nothing. */
  it("pins the section head and stops the deck at the same rule", () => {
    expect(html).toContain("band-pin-shell");
    expect(html).toContain("band-pin");
    // The deck reads the height the stylesheet authored once, not its own copy.
    expect(html).toContain("--deck-top:calc(var(--nav-shell-h,62px)+var(--band-pin-h,0px))");
    expect(html).not.toContain("--deck-top:calc(var(--nav-shell-h,62px)+0.75rem)");
  });

  /* DIG-3311: title and takeaway must pin as one block, not separately —
     a takeaway left outside the pinned head slides in behind it on scroll
     instead of staying put beside the title. */
  it("pins the eyebrow, the title, and the takeaway together", () => {
    const headerAt = html.indexOf("band-pin\"");
    expect(headerAt).toBeGreaterThanOrEqual(0);
    const headerEnd = html.indexOf("</header>", headerAt);
    expect(html.slice(headerAt, headerEnd)).toContain("Agent orchestration");
    expect(html.slice(headerAt, headerEnd)).toContain("not a live run");
  });
});
