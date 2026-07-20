'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { buildPipelineDayData, fanoutIdForKey } from '@/lib/pipeline-graph-data';
import type { PipelineDayData } from '@/lib/pipeline-graph-data';
import { PIPELINE_TOPOLOGY } from '@/lib/pipeline-topology';
import type { PipelineStageId } from '@/lib/pipeline-topology';
import type { ExpansionState, LaidOutNode } from '@/lib/pipeline-layout';
import type { PipelineStage } from '@/lib/pipeline-links';
import { DIGEST_DOCUMENT_KEYS, parsePipelineParams, resolvePresentDigestKey } from '@/lib/pipeline-links';
import type { RegimeChip } from '@/lib/render-pipeline-payloads';
import { regimeChipsFromMacroPayload, summarizeRecommendedPortfolio } from '@/lib/render-pipeline-payloads';
import PipelineSummaryStrip from './PipelineSummaryStrip';
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

  // Summary strip state
  const [headline, setHeadline] = useState<string | null>(null);
  const [regimeChips, setRegimeChips] = useState<RegimeChip[]>([]);
  const [decision, setDecision] = useState<string | null>(null);

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
      // Reset before the fetch, not just on success — otherwise switching to a
      // date with no digest/rebalance/macro doc silently keeps showing the
      // PREVIOUS date's headline/decision/chips.
      setHeadline(null);
      setDecision(null);
      setRegimeChips([]);
      setDayLoading(true);

      try {
        const { createClient } = await import('@supabase/supabase-js');
        const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
        const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
        if (!url || !key) return;

        const supabase = createClient(url, key);
        const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

        // Independent reads — run them together instead of one round-trip at a time.
        const [datesRes, docsRes, digestRes, rebalanceRes, macroRes] = await Promise.all([
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
          // The digest is published as `digest` on baseline days, `digest-delta`
          // on delta days (the majority of days). A backfilled date can carry
          // BOTH keys — `.maybeSingle()` errors on >1 row and blanked the
          // headline, so fetch both and pick by DIGEST_DOCUMENT_KEYS precedence.
          supabase
            .from('documents')
            .select('document_key, payload')
            .in('document_key', DIGEST_DOCUMENT_KEYS)
            .eq('date', selectedDate),
          supabase
            .from('documents')
            .select('payload')
            .eq('document_key', 'pm-rebalance')
            .eq('date', selectedDate)
            .maybeSingle(),
          supabase
            .from('documents')
            .select('payload')
            .eq('document_key', 'macro')
            .eq('date', selectedDate)
            .maybeSingle(),
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

        // Headline comes from the digest's structured `headline` field — pipeline
        // documents leave `documents.content` empty and carry everything in `payload`.
        const digestRows = (digestRes.data ?? []) as { document_key: string; payload: unknown }[];
        const digestRow = DIGEST_DOCUMENT_KEYS
          .map((k) => digestRows.find((r) => r.document_key === k))
          .find(Boolean);
        const digestPayload = digestRow?.payload as Record<string, unknown> | undefined;
        const headlineText = typeof digestPayload?.headline === 'string' ? digestPayload.headline.trim() : '';
        if (headlineText) setHeadline(headlineText);

        // Decision chip: summarize the day's PM rebalance book (target weights),
        // not decision_log (a per-ticker analyst-call audit trail, not a per-day summary).
        const summary = summarizeRecommendedPortfolio(rebalanceRes.data?.payload);
        if (summary) {
          setDecision(`${summary.holdingsCount} holdings · ${summary.investedPct.toFixed(0)}% invested`);
        }

        setRegimeChips(regimeChipsFromMacroPayload(macroRes.data?.payload));
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
    <div className="flex flex-col flex-1 min-h-0 min-w-0">
      {/* Run context: the day's read and state paired with temporal navigation. */}
      <div className="border-y border-hair bg-surface/70 px-4 py-3 md:px-6">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <PipelineSummaryStrip
            headline={headline}
            regimeChips={regimeChips}
            decision={decision}
            loading={dayLoading}
          />
          <PipelineDaySelector
            dates={availableDates}
            value={selectedDate}
            onChange={handleDateChange}
          />
        </div>
        {noRunForDate && (
          <p className="mt-2 border-t border-hair pt-2 font-mono text-xs text-ink-mute" role="status">
            No pipeline run recorded for this date — the graph below shows the
            expected shape, not real output.
          </p>
        )}
      </div>

      {/* Canvas + NodeDetail */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col md:flex-row">
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
    </div>
  );
}
