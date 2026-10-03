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

    const holdings = renderToStaticMarkup(<DeskPage path="/portfolio/holdings" />);
    expect(holdings).toContain("Holdings · by sleeve");

    const attribution = renderToStaticMarkup(<DeskPage path="/portfolio/attribution" />);
    expect(attribution).toContain("Attribution");
    expect(attribution).toContain('data-route="/attribution"');

    const ledger = renderToStaticMarkup(<DeskPage path="/portfolio/ledger" />);
    expect(ledger).toContain("Ledger · position events");
    expect(ledger).toContain('data-route="/ledger?limit=50"');
    expect(ledger).toContain("Cash ledger");
    expect(ledger).toContain('data-route="/ledger/cash"');

    const pipeline = renderToStaticMarkup(<DeskPage path="/pipeline" />);
    expect(pipeline).toContain('data-block="pl-narrative"');
    expect(pipeline).toContain("Run narrative");
    expect(pipeline).not.toContain("Run health");

    const strategies = renderToStaticMarkup(<DeskPage path="/strategies" />);
    expect(strategies).toContain('data-route="/strategies/summary"');
    expect(strategies).toContain("Strategies · summary");

    const fx = renderToStaticMarkup(<DeskPage path="/fx" />);
    expect(fx).toContain("This page is not on the public desk.");
    expect(fx).not.toMatch(/fx hub|12x/i);
    expect(fx).not.toContain("/fx/summary");
  });
});
