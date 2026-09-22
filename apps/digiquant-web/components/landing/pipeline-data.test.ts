import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { LIVE_ORDERS, PIPELINE_PHASES, PORTFOLIO_PHASES, RESEARCH_PHASES } from "../../app/_pipeline";

/**
 * Pins the site's pipeline data to the canonical backend graph (#4430).
 *
 * A literal mirror is the only practical option here: the site cannot import
 * the Python graph, so this test re-reads
 * `digiquant/src/digiquant/portfolio/graph.py`, extracts the
 * `phases.append(...)` call sequence from `build_portfolio_phases_thesis()`,
 * and asserts the site's `PORTFOLIO_PHASES` ids match it in order. A renamed,
 * reordered, added or dropped backend phase fails loudly instead of shipping
 * a stale count or a false chip. (This exact drift — the coverage director
 * missing and risk sizing mislabelled — shipped once already.)
 *
 * The BUILDER_TO_CHIP map below is itself a manual mirror of what each
 * builder constructs; if a builder is renamed in the graph, update the map
 * key to the new name (the regex will stop matching otherwise).
 */
const GRAPH_PATH = path.resolve(
  __dirname,
  "../../../../digiquant/src/digiquant/portfolio/graph.py",
);
/** Builder call in graph.py → chip id in PORTFOLIO_PHASES. */
const BUILDER_TO_CHIP: Record<string, string> = {
  build_h1_thesis_review: "h1",
  build_h2_market_thesis_exploration: "h2",
  build_h3_thesis_vehicle_map: "h3",
  build_h4_opportunity_screener: "h4",
  build_coverage_director: "h45",
  build_h5_from_state: "h5",
  build_h6_from_state: "h6",
  build_h7_pm_direction: "h7",
  _build_h8_risk_sizing: "h8",
  build_h9_commit_run: "h9",
};

function graphPhaseBuilders(): string[] {
  const src = readFileSync(GRAPH_PATH, "utf8");
  const body = src.split("def build_portfolio_phases_thesis(")[1].split(/^def /m)[0];
  return [...body.matchAll(/phases\.append\(\s*(\w+)/g)].map((m) => m[1]);
}

describe("pipeline data file vs canonical portfolio graph", () => {
  it("mirrors the graph's phase sequence chip-for-chip, in order", () => {
    const builders = graphPhaseBuilders();
    expect(builders.length).toBeGreaterThan(0);
    // Every graph append must have a known chip mapping — an unmapped (new or
    // renamed) builder fails here, not silently on the site.
    for (const b of builders) {
      expect(Object.keys(BUILDER_TO_CHIP)).toContain(b);
    }
    expect(PORTFOLIO_PHASES.map((p) => p.id)).toEqual(builders.map((b) => BUILDER_TO_CHIP[b]));
  });

  it("ships ten research and ten portfolio phases (twenty total)", () => {
    // Research entries are site-level group labels over the research graph's
    // daily list (preflight, triage, phase1–7, publish), not a mirror — only
    // the count is asserted here. The portfolio sequence above is the pinned one.
    expect(RESEARCH_PHASES.length).toBe(10);
    expect(PORTFOLIO_PHASES.length).toBe(10);
    expect(PIPELINE_PHASES.length).toBe(20);
  });

  it("keeps live orders at zero by design", () => {
    expect(LIVE_ORDERS).toBe(0);
  });
});
