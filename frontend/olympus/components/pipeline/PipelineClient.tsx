'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { buildPipelineDayData, fanoutIdForKey } from '@/lib/pipeline-graph-data';
import type { PipelineDayData } from '@/lib/pipeline-graph-data';
import { PIPELINE_TOPOLOGY } from '@/lib/pipeline-topology';
import type { PipelineStageId } from '@/lib/pipeline-topology';
import type { ExpansionState, LaidOutNode } from '@/lib/pipeline-layout';
import type { PipelineStage } from '@/lib/pipeline-links';
import { parsePipelineParams, resolvePresentDigestKey } from '@/lib/pipeline-links';
import PipelineDaySelector from './PipelineDaySelector';
import PipelineCanvas from './PipelineCanvas';
import PipelineNodeDetail from './PipelineNodeDetail';

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

/** The owning stage + `${stageId}:${subId}` fan-out key for a fan-out id, from the static topology. */
function fanoutOwner(fanoutId: string): { stageId: PipelineStageId; fanoutKey: string } | null {
  for (const stage of PIPELINE_TOPOLOGY) {
    for (const sub of stage.subSteps) {
      if (sub.fanout?.id === fanoutId) return { stageId: stage.id, fanoutKey: `${stage.id}:${sub.id}` };
    }
  }
  return null;
}

function buildInitialExpansion(
  stage: PipelineStage | undefined,
  node: string | undefined,
): ExpansionState {
  const expandedStages = new Set<PipelineStageId>(stage ? [stage] : []);
  const expandedFanouts = new Set<string>();

  // Deep-link straight to a fan-out branch (e.g. ?node=analyst/QQQ): expand the owning
  // stage + fan-out so the branch renders and the in-graph selection highlight shows.
  if (node) {
    const fanoutId = fanoutIdForKey(node);
    const owner = fanoutId ? fanoutOwner(fanoutId) : null;
    if (owner) {
      expandedStages.add(owner.stageId);
      expandedFanouts.add(owner.fanoutKey);
    }
  }

  return { expandedStages, expandedFanouts };
}

export default function PipelineClient() {
  // Static export (`output: 'export'`) — there is no server to hand this page a
  // `searchParams` prop, so deep links (`?date=&stage=&node=`) must be read
  // client-side, same as `/why` (`components/why/why-client.tsx`). Must be
  // Suspense-wrapped by the caller (`app/pipeline/page.tsx`) per Next.js's rules
  // for `useSearchParams`.
  const searchParams = useSearchParams();
  const params = useMemo(
    () => parsePipelineParams(searchParams),
    [searchParams],
  );

  const [selectedDate, setSelectedDate] = useState(params.date ?? today());
  const [availableDates, setAvailableDates] = useState<string[]>([selectedDate]);
  // Only auto-snap the landing date while the user hasn't chosen one: seeding
  // with UTC "today" opens on a date with zero documents every day between
  // 00:00 UTC and the ~12:00 UTC run (US evenings) — snap to the latest real
  // run instead. An explicit ?date= deep link or a selector click wins.
  const dateExplicit = useRef(Boolean(params.date));
  const [dayLoading, setDayLoading] = useState(true);
  const [dayData, setDayData] = useState<PipelineDayData>({
    fanoutCounts: {},
    fanoutKeys: {},
    presentKeys: new Set(),
  });

  // Node detail
  const [activeNode, setActiveNode] = useState<LaidOutNode | null>(null);
  const [activeDocumentKey, setActiveDocumentKey] = useState<string | null>(params.node ?? null);

  const initialExpansion = useMemo(
    () => buildInitialExpansion(params.stage, params.node),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // Load documents for the selected date
  useEffect(() => {
    let cancelled = false;

    void (async () => {
      setDayLoading(true);

      try {
        const { createClient } = await import('@supabase/supabase-js');
        const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
        const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
        if (!url || !key) return;

        const supabase = createClient(url, key);
        const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

        // Independent reads — run them together instead of one round-trip at a time.
        const [datesRes, docsRes] = await Promise.all([
          // Run dates come from daily_snapshots (exactly one row per run day).
          // Deriving them from `documents` selects EVERY row (~40-60/day), and
          // the PostgREST 1000-row default cap silently truncated the oldest
          // dates out of the 30-day window.
          supabase
            .from('daily_snapshots')
            .select('date')
            .gte('date', thirtyDaysAgo)
            .order('date', { ascending: false }),
          supabase.from('documents').select('document_key').eq('date', selectedDate),
        ]);

        if (cancelled) return;

        if (datesRes.data) {
          const uniqueDates = [...new Set((datesRes.data as { date: string }[]).map((r) => r.date))]
            .sort()
            .reverse();
          if (uniqueDates.length > 0) {
            setAvailableDates(uniqueDates);
            // Landing-date snap: no explicit choice + the seeded date has no
            // run → jump to the latest run. Runs at most once per load (after
            // the snap, selectedDate IS in uniqueDates).
            if (!dateExplicit.current && !uniqueDates.includes(selectedDate)) {
              setSelectedDate(uniqueDates[0]);
              return; // the effect re-runs for the snapped date
            }
          }
        }

        if (docsRes.data) {
          setDayData(buildPipelineDayData(docsRes.data as { document_key: string }[]));
        }

      } catch {
        // Supabase not configured or no data — degrade gracefully
      } finally {
        if (!cancelled) setDayLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [selectedDate]);

  // A '?node=digest' deep link (from Overview / the command palette, which don't
  // know today's baseline-vs-delta cadence) is a sentinel, not necessarily this
  // day's real key — derive the actual key to fetch/highlight once the day's
  // documents load, rather than storing it (avoids a setState-in-effect).
  const resolvedActiveDocumentKey = useMemo(() => {
    if (activeDocumentKey !== 'digest') return activeDocumentKey;
    return resolvePresentDigestKey(dayData) ?? activeDocumentKey;
  }, [activeDocumentKey, dayData]);

  const handleNodeActivate = useCallback((node: LaidOutNode) => {
    setActiveNode(node);
    setActiveDocumentKey(node.documentKey ?? null);
  }, []);

  const handleDetailClose = useCallback(() => {
    setActiveNode(null);
    setActiveDocumentKey(null);
  }, []);

  const handleDateChange = useCallback((date: string) => {
    dateExplicit.current = true;
    setSelectedDate(date);
  }, []);

  const noRunForDate = !dayLoading && dayData.presentKeys.size === 0;

  return (
    <section
      data-testid="pipeline-workspace"
      aria-label="Daily decision pipeline"
      className="flex min-h-0 min-w-0 flex-1 flex-col bg-surface"
    >
      <header
        data-testid="pipeline-command-band"
        className="flex min-h-12 items-center justify-end border-y border-hair bg-surface px-4 py-2 md:px-4"
      >
        <h1 className="sr-only">Pipeline</h1>
        {noRunForDate && (
          <p className="mr-auto font-mono text-xs text-ink-mute" role="status">
            No run recorded — showing the expected pipeline.
          </p>
        )}
        <PipelineDaySelector
          dates={availableDates}
          value={selectedDate}
          onChange={handleDateChange}
        />
      </header>

      <div
        data-testid="pipeline-workflow"
        className="flex min-h-[calc(100dvh-125px)] min-w-0 flex-1 flex-col md:min-h-0 md:flex-row"
      >
        <PipelineCanvas
          day={dayData}
          initialExpansion={initialExpansion}
          selectedNodeId={activeNode?.id ?? resolvedActiveDocumentKey ?? undefined}
          onNodeActivate={handleNodeActivate}
        />

        {(activeNode !== null || resolvedActiveDocumentKey !== null) && (
          <PipelineNodeDetail
            node={activeNode}
            documentKey={resolvedActiveDocumentKey}
            date={selectedDate}
            onClose={handleDetailClose}
          />
        )}
      </div>
    </section>
  );
}
