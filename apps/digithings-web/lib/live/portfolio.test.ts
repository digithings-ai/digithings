import { describe, expect, it } from "vitest";
import {
  ACCOUNTING_NAV_COLUMNS,
  ACCOUNTING_NAV_VIEW,
  cagrPct,
  fetchBenchmark,
  fetchNav,
  fetchStrategies,
  isDcaStrategy,
  publishedNavPoints,
} from "./portfolio";

/**
 * The #3935 stitch. Indexing every row from the legacy anchor is +11.849%.
 * The finalized run alone is +0.993%. The landing page has no since-inception
 * label; these ratios are what `nav[0]` indexing produces on each series.
 */
const SEAM_ROWS = [
  { date: "2026-09-06", nav: 100, source: "legacy_nav_history" },
  { date: "2026-09-07", nav: 99.92, source: "legacy_nav_history" },
  { date: "2026-09-08", nav: 110.74928206, source: "finalized_accounting" },
  { date: "2026-09-09", nav: 111.84928206, source: "finalized_accounting" },
];

function sinceInceptionPct(points: { nav: number }[]): number {
  return (points[points.length - 1].nav / points[0].nav - 1) * 100;
}

/**
 * The live layer's pure parts plus its degrade path.
 *
 * The degrade path is the part worth pinning: this app is a static export, so
 * every read must return empty — never throw — when the public env is absent,
 * which is the state of a local build and of any deploy before the Cloudflare
 * Pages project has the two vars set. A throw here would take the landing page
 * down on a missing secret.
 */
describe("live portfolio reads", () => {
  it("computes an annual rate from a dated total return", () => {
    expect(cagrPct(100, "2023-01-01", "2024-01-01")).toBeCloseTo(100, 0);
    expect(cagrPct(0, "2023-01-01", "2024-01-01")).toBeCloseTo(0, 5);
  });

  it("returns null rather than a fabricated rate for a bad period", () => {
    expect(cagrPct(50, "2024-01-01", "2023-01-01")).toBeNull();
    expect(cagrPct(50, "not a date", "2024-01-01")).toBeNull();
    // A -150% total return has no real root: must be null, not NaN.
    expect(cagrPct(-150, "2023-01-01", "2024-01-01")).toBeNull();
  });

  it("spots the DCA strategy the way the library does", () => {
    expect(isDcaStrategy("btc_sdca")).toBe(true);
    expect(isDcaStrategy("btc_dca")).toBe(true);
    expect(isDcaStrategy("btc_slapper")).toBe(false);
  });

  it("publishes finalized rows and drops the legacy prefix", () => {
    const bridged = SEAM_ROWS.map((row) => ({ date: row.date, nav: row.nav }));
    // Indexing the stitch from the first row is +11.849%, not the finalized run.
    expect(sinceInceptionPct(bridged)).toBeCloseTo(11.84928206, 5);

    const published = publishedNavPoints(SEAM_ROWS);
    expect(published.map((point) => point.date)).toEqual(["2026-09-08", "2026-09-09"]);
    expect(sinceInceptionPct(published)).toBeCloseTo(0.993234, 3);
    expect(sinceInceptionPct(published)).not.toBeCloseTo(sinceInceptionPct(bridged), 0);
  });

  it("keeps a finalized run when a provisional nav_history tip is appended", () => {
    // Latest-source-run cut returned only the tip. One point, and the landing
    // chart falls through to the synthetic example. The tip must not be the series.
    const rows = [
      { date: "2026-09-08", nav: 110.74928206, source: "finalized_accounting" },
      { date: "2026-10-02", nav: 111.2, source: "finalized_accounting" },
      { date: "2026-10-03", nav: 112.4, source: "legacy_nav_history" },
    ];
    const published = publishedNavPoints(rows);
    expect(published).toEqual([
      { date: "2026-09-08", nav: 110.74928206 },
      { date: "2026-10-02", nav: 111.2 },
    ]);
    expect(published).not.toEqual([{ date: "2026-10-03", nav: 112.4 }]);
    expect(published.length).toBeGreaterThan(1);
  });

  it("keeps finalized rows on both sides of a one-day legacy hole", () => {
    const rows = [
      { date: "2026-09-08", nav: 110, source: "finalized_accounting" },
      { date: "2026-09-09", nav: 111, source: "finalized_accounting" },
      { date: "2026-09-10", nav: 50, source: "legacy_nav_history" },
      { date: "2026-09-11", nav: 112, source: "finalized_accounting" },
      { date: "2026-09-12", nav: 113, source: "finalized_accounting" },
    ];
    expect(publishedNavPoints(rows).map((point) => point.date)).toEqual([
      "2026-09-08",
      "2026-09-09",
      "2026-09-11",
      "2026-09-12",
    ]);
  });

  it("reads the finalized view, which has no series_seam column", () => {
    expect(ACCOUNTING_NAV_VIEW).toBe("public_finalized_nav");
    expect(ACCOUNTING_NAV_COLUMNS).not.toContain("series_seam");
  });

  it("drops rows that cannot be a NAV point", () => {
    expect(
      publishedNavPoints([
        { date: "2026-09-08", nav: "nope", source: "finalized_accounting" },
        { date: 1, nav: 10 },
        null,
      ]),
    ).toEqual([]);
  });

  it("degrades to empty, without throwing, when the env is absent", async () => {
    await expect(fetchNav()).resolves.toEqual([]);
    await expect(fetchStrategies(["btc_slapper"])).resolves.toEqual([]);
    await expect(fetchBenchmark("2024-01-01")).resolves.toEqual([]);
  });
});
