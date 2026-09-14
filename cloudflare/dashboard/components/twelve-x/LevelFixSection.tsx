'use client';

import { useEffect, useState } from 'react';
import { getFxFixSeries } from '@/lib/twelve-x/fetch';
import {
  buildLevelFixSeries,
  fixWindowDays,
  normalizeFixPair,
  type FxFixPoint,
  type LevelFixSeries,
} from '@/lib/twelve-x/level-vs-fix';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';
import LevelFixChart from './LevelFixChart';

/** Module-level promise cache so N rows on one pair share a single fetch. */
const fixCache = new Map<string, Promise<Record<string, FxFixPoint[]>>>();

/**
 * Shared fix-history fetch for one pair+window. A transient failure resolves
 * empty for the current caller but is evicted, so the next mount retries
 * instead of pinning the empty series for the module lifetime (LOW3).
 */
export function fixesForPair(pair: string, windowDays: number): Promise<Record<string, FxFixPoint[]>> {
  const key = normalizeFixPair(pair);
  const cacheKey = `${key}::${windowDays}`;
  const cached = fixCache.get(cacheKey);
  if (cached) return cached;
  const pending = getFxFixSeries([pair], windowDays).then(
    (result) => result,
    () => {
      if (fixCache.get(cacheKey) === pending) fixCache.delete(cacheKey);
      return { [key]: [] as FxFixPoint[] };
    },
  );
  fixCache.set(cacheKey, pending);
  return pending;
}

/**
 * Self-loading level-vs-fix block: fetches the pair's fix history, builds the
 * series against the idea's published levels (+ eval anchors when provided),
 * and renders {@link LevelFixChart}. `evalRow` is optional — Today ideas have
 * no eval yet, so their charts show levels + fix without entry/exit markers.
 */
export function LevelFixSection({
  idea,
  evalRow = null,
}: {
  idea: FxTradeIdeaRow;
  evalRow?: FxIdeaEvalRow | null;
}) {
  const [series, setSeries] = useState<LevelFixSeries | null>(null);

  useEffect(() => {
    let cancelled = false;
    fixesForPair(idea.pair, fixWindowDays(idea.run_date)).then((byPair) => {
      if (cancelled) return;
      setSeries(
        buildLevelFixSeries(idea, evalRow, byPair[normalizeFixPair(idea.pair)] ?? []),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [idea, evalRow]);

  if (!series) {
    return (
      <p className="font-mono text-[10px] text-ink-mute" data-testid="level-fix-loading">
        Loading fix series…
      </p>
    );
  }
  return <LevelFixChart series={series} />;
}

export default LevelFixSection;
