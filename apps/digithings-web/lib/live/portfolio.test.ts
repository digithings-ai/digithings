import { describe, expect, it } from "vitest";
import { cagrPct, fetchBenchmark, fetchNav, fetchStrategies, isDcaStrategy } from "./portfolio";

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

  it("degrades to empty, without throwing, when the env is absent", async () => {
    await expect(fetchNav()).resolves.toEqual([]);
    await expect(fetchStrategies(["btc_slapper"])).resolves.toEqual([]);
    await expect(fetchBenchmark("2024-01-01")).resolves.toEqual([]);
  });
});
