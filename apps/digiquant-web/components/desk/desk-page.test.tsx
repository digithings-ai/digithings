import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DeskPage } from "./desk-page";

describe("mounted desk pages", () => {
  it("renders the page components for the live desk paths", () => {
    const brief = renderToStaticMarkup(<DeskPage path="/brief" />);
    expect(brief).toContain("Brief · scoreboard");
    expect(brief).toContain('class="rail"');

    const portfolio = renderToStaticMarkup(<DeskPage path="/portfolio" />);
    expect(portfolio).toContain("Portfolio · envelope");

    const pipeline = renderToStaticMarkup(<DeskPage path="/pipeline" />);
    expect(pipeline).toContain('data-block="pl-narrative"');
    expect(pipeline).toContain("Run narrative");
    expect(pipeline).not.toContain("Run health");

    const strategies = renderToStaticMarkup(<DeskPage path="/strategies" />);
    expect(strategies).toContain('data-route="/strategies/summary"');
    expect(strategies).toContain("Strategies · summary");

    const fx = renderToStaticMarkup(<DeskPage path="/fx" />);
    expect(fx).toContain("FX hub · summary");
    expect(fx).toContain("/fx/summary");
  });
});
