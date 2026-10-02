"use client";

import { useEffect, useState } from "react";
import {
  benchmarkFromBenchmarks,
  cardFromPerformance,
  officialGet,
  portfolioFromPerformance,
  strategiesFromCatalog,
  type NavPoint,
  type PricePoint,
  type TearsheetCardRead,
} from "./officialBand";

export interface OfficialBandRead {
  loading: boolean;
  note: string | null;
  nav: NavPoint[];
  benchmark: PricePoint[];
  cards: TearsheetCardRead[];
}

const EMPTY: OfficialBandRead = {
  loading: false,
  note: null,
  nav: [],
  benchmark: [],
  cards: [],
};

/** How many library cards the band asks for. The rest stay on digiquant.io. */
const CARD_LIMIT = 4;
const BENCHMARK = "SPY";

/**
 * Mount-only. The site is a static export, so a read during render would bake
 * a stale series into the bundle.
 */
export function useOfficialBand(): OfficialBandRead {
  const [read, setRead] = useState<OfficialBandRead>({ ...EMPTY, loading: true });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [performance, benchmarks, catalog] = await Promise.all([
        officialGet("/performance"),
        officialGet("/benchmarks", { tickers: BENCHMARK }),
        officialGet("/strategies"),
      ]);
      if (cancelled) return;
      const nav = performance.ok ? portfolioFromPerformance(performance.body) : [];
      const benchmark = benchmarks.ok ? benchmarkFromBenchmarks(benchmarks.body, BENCHMARK) : [];
      const listed = catalog.ok ? strategiesFromCatalog(catalog.body).slice(0, CARD_LIMIT) : [];
      const sheets = await Promise.all(
        listed.map((strategy) => officialGet("/strategies/default/performance", { id: strategy.id })),
      );
      if (cancelled) return;
      const cards = sheets
        .map((sheet) => (sheet.ok ? cardFromPerformance(sheet.body) : null))
        .filter((card): card is TearsheetCardRead => card !== null);
      const note =
        nav.length < 2 && cards.length === 0
          ? performance.ok
            ? null
            : performance.reason
          : null;
      setRead({ loading: false, note, nav, benchmark, cards });
    })().catch(() => {
      if (!cancelled) {
        setRead({
          ...EMPTY,
          note: "The official API did not respond.",
        });
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return read;
}
