'use client';

import { useEffect, useState } from 'react';
import AtlasLoader from '@/components/AtlasLoader';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import { OlympusTearsheetView } from '@/components/tearsheet/OlympusTearsheetView';
import { fetchOlympusTearsheet } from '@/lib/observability-queries';
import type { OlympusTearsheet } from '@/components/tearsheet/types';

/**
 * Performance — the hybrid, exportable tear sheet for the single strategy
 * "Olympus": a live-NAV track + an Olympus-specific decision track-record track,
 * each degrading independently, plus the relocated Attribution diagnostics.
 * Empty-state-first; window.print() export enabled in all states.
 */
export default function PerformancePage() {
  const [data, setData] = useState<OlympusTearsheet | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchOlympusTearsheet()
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load performance data');
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className={`${SUBPAGE_MAX} ts-page flex-1 py-4 md:py-6`}>
      {error ? (
        <p className="ts-status ts-status-error">{error}</p>
      ) : !data ? (
        <AtlasLoader fullScreen={false} />
      ) : (
        <OlympusTearsheetView data={data} />
      )}
    </div>
  );
}
