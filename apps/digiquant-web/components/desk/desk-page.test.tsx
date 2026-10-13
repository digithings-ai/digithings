import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DeskAccess } from "./desk-access";
import type { Manifest } from "./desk-manifest";
import { DeskPage, DeskRouteBody } from "./desk-page";

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

    const theses = renderToStaticMarkup(<DeskPage path="/portfolio/theses" />);
    expect(theses).toContain("Theses");
    expect(theses).toContain('data-route="/theses"');
    expect(theses).toContain("Signals to resolve");
    expect(theses).toContain('data-route="/theses/signals"');

    const tearsheet = renderToStaticMarkup(<DeskPage path="/portfolio/tearsheet" />);
    expect(tearsheet).toContain("Performance · tearsheet");
    expect(tearsheet).toContain('data-route="/performance"');
    expect(tearsheet).toContain("NAV · by date");
    expect(tearsheet).toContain('data-route="/nav-series"');
    expect(tearsheet).toContain("Benchmarks · aligned");
    expect(tearsheet).toContain('data-route="/benchmarks"');

    const pipeline = renderToStaticMarkup(<DeskPage path="/pipeline" />);
    expect(pipeline).toContain("Run health");
    expect(pipeline).toContain('data-route="/pipeline/runs/latest/health"');
    expect(pipeline).toContain("Run narrative");
    expect(pipeline).toContain('data-route="/pipeline/runs/latest/narrative"');
    expect(pipeline).toContain("Artifact ledger");
    expect(pipeline).toContain('data-route="/pipeline/runs/latest/artifacts"');
    expect(pipeline).toContain("Graph · nodes");
    expect(pipeline).toContain('data-route="/pipeline/runs/latest/graph"');
    expect(pipeline).toContain("Node document");
    expect(pipeline).toContain('data-route="/pipeline/runs/latest/nodes/selected/document"');
    expect(pipeline).toContain("Call trace");
    expect(pipeline).toContain('data-route="/pipeline/runs/latest/trace"');

    const strategies = renderToStaticMarkup(<DeskPage path="/strategies" />);
    expect(strategies).toContain("Strategies · summary");
    expect(strategies).toContain('data-route="/strategies/summary"');
    expect(strategies).toContain("Catalog");
    expect(strategies).toContain('data-route="/strategies"');
    expect(strategies).toContain("My deployments");
    expect(strategies).toContain('data-route="/strategies/deployments"');

    const deploy = renderToStaticMarkup(<DeskPage path="/strategies/deploy" />);
    expect(deploy).toContain("Deployment targets");
    expect(deploy).toContain('data-route="/strategies/targets"');
    expect(deploy).toContain("Deploy · plan");
    expect(deploy).toContain('data-route="/strategies/deploy-flow"');
    expect(deploy).toContain("Target · paper");
    expect(deploy).toContain('data-route="/strategies/default/deploy-draft"');

    const detail = renderToStaticMarkup(<DeskPage path="/strategies/detail" />);
    expect(detail).toContain("Overview");
    expect(detail).toContain('data-route="/strategies/default"');
    expect(detail).toContain("Parameters");
    expect(detail).toContain('data-route="/strategies/default/parameters"');
    expect(detail).toContain("Tearsheet");
    expect(detail).toContain("Paper track record");
    expect(detail).toContain('data-route="/strategies/default/performance"');
    expect(detail).toContain("Runs");
    expect(detail).toContain('data-route="/strategies/default/runs"');

    const fx = renderToStaticMarkup(<DeskPage path="/fx" />);
    expect(fx).toContain("This page is not on the public desk.");
    expect(fx).not.toMatch(/fx hub|12x/i);
    expect(fx).not.toContain("/fx/summary");
  });

  it("draws an invite page only when the manifest grants it", () => {
    const desk = (access: "granted" | "locked"): Manifest => ({
      caller: { tier: "enterprise", groups: [] },
      desks: [{ id: "fx", label: "FX Hub", blurb: "", access, pages: [{ path: "/fx", label: "FX Hub", access }] }],
    });
    const granted = renderToStaticMarkup(
      <DeskAccess manifest={desk("granted")}>
        <DeskRouteBody path="/fx" />
      </DeskAccess>,
    );
    expect(granted).not.toContain("This page is not on the public desk.");
    expect(granted).toContain("FX hub · summary");
    const locked = renderToStaticMarkup(
      <DeskAccess manifest={desk("locked")}>
        <DeskRouteBody path="/fx" />
      </DeskAccess>,
    );
    expect(locked).toContain("This page is not on the public desk.");
    expect(locked).not.toContain("/fx/summary");
  });
});
