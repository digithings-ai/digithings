/**
 * The digiquant band must never render an empty strategy rail or drop its
 * book chart when the live read is withheld.
 *
 * dashboard-api refuses both live reads (`/nav-series`,
 * `/v1/tables/strategy_tearsheets`) to anonymous callers (403, tier policy),
 * so the read is configured yet empty for every public visitor. Gating the
 * fallbacks on `live.configured` (rather than on the data) left the live
 * site with an empty rail and no chart — DIG-3552. These guards pin the
 * data-gated shape: empty read → badged example fallback, never nothing.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const src = readFileSync(fileURLToPath(new URL("./QuantSection.tsx", import.meta.url)), "utf8");

describe("digiquant band live-read fallback", () => {
  it("falls back to the example strategy cards when the live read is empty", () => {
    expect(src).toContain(
      "live.strategies.length > 0 ? live.strategies.map(liveStrategyCard) : STRATEGIES",
    );
  });

  it("falls back to the example book series when there is no live index", () => {
    expect(src).toContain(
      "liveIndex ?? { series: PERFORMANCE_SERIES, fullSpan: FULL_SPAN }",
    );
  });

  it("always renders the book chart (never a conditional that drops it)", () => {
    expect(src).toContain("<Book series={book.series}");
    expect(src).not.toContain("{book ? (");
  });

  it("badges the fallback as example, on the label and on each card", () => {
    expect(src).toContain('"strategies · example"');
    expect(src).toContain('{showExampleBadge ? " · example" : ""}');
  });

  it("never gates cards or book on configuration alone", () => {
    expect(src).not.toContain("usingLive");
  });
});
