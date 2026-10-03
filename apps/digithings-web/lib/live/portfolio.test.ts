import { describe, expect, it } from "vitest";
import {
  cagrPct,
  fetchBenchmark,
  fetchNav,
  fetchStrategies,
  isDcaStrategy,
  publishedNavPoints,
} from "./portfolio";

/**
 * The stitched public view (#3767 / #3935). Indexing every row from the legacy
 * anchor bridges the source flip and prints a return the finalized book did
 * not earn.
 */
const SEAM_ROWS = [
  { date: "2026-09-06", nav: 100, source: "legacy_nav_history", series_seam: false },
  { date: "2026-09-07", nav: 99.92, source: "legacy_nav_history", series_seam: false },
  { date: "2026-09-08", nav: 110.74928206, source: "finalized_accounting", series_seam: true },
  { date: "2026-09-09", nav: 111.84928206, source: "finalized_accounting", series_seam: false },
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

  it("rebases the published series on the current source run", () => {
    const bridged = SEAM_ROWS.map((row) => ({ date: row.date, nav: row.nav }));
    // The old read kept every row and indexed from the legacy anchor, so
    // since-inception spanned the seam (~+11.8% instead of the finalized run).
    expect(sinceInceptionPct(bridged)).toBeCloseTo((111.84928206 / 100 - 1) * 100, 5);

    const published = publishedNavPoints(SEAM_ROWS);
    expect(published.map((point) => point.date)).toEqual(["2026-09-08", "2026-09-09"]);
    expect(sinceInceptionPct(published)).toBeCloseTo(
      (111.84928206 / 110.74928206 - 1) * 100,
      5,
    );
    expect(sinceInceptionPct(published)).not.toBeCloseTo(sinceInceptionPct(bridged), 0);
  });

  it("keeps a single source run intact, including when the seam flag is absent", () => {
    const oneRun = SEAM_ROWS.slice(2).map((row) => ({
      date: row.date,
      nav: row.nav,
      source: row.source,
    }));
    expect(publishedNavPoints(oneRun).map((point) => point.date)).toEqual([
      "2026-09-08",
      "2026-09-09",
    ]);
    // A source flip is enough on its own — the boolean is additive.
    const unlabeled = SEAM_ROWS.map((row) => ({
      date: row.date,
      nav: row.nav,
      source: row.source,
    }));
    expect(publishedNavPoints(unlabeled).map((point) => point.date)).toEqual([
      "2026-09-08",
      "2026-09-09",
    ]);
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
