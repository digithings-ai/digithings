'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { ChartGantt, Files, ListTree } from 'lucide-react';
import { Button } from '@digithings/ui/ui';
import { buildPipelineDayData, fanoutIdForKey } from '@/lib/pipeline-graph-data';
import type { PipelineDayData } from '@/lib/pipeline-graph-data';
import { PIPELINE_TOPOLOGY } from '@/lib/pipeline-topology';
import type { PipelineStageId } from '@/lib/pipeline-topology';
import type { ExpansionState, LaidOutNode } from '@/lib/pipeline-layout';
import type { PipelineStage } from '@/lib/pipeline-links';
import {
  parsePipelineParams,
  resolvePresentDigestKey,
  stageForDocumentKey,
} from '@/lib/pipeline-links';
import PipelineDaySelector from './PipelineDaySelector';
import PipelineCanvas from './PipelineCanvas';
import PipelineNodeDetail from './PipelineNodeDetail';
import PipelineArtifactLedger from './PipelineArtifactLedger';
import PipelineTraceLedger from './PipelineTraceLedger';
import PipelineRunHealth from './PipelineRunHealth';
import PipelineRunStrip from './PipelineRunStrip';
import PipelineTimeline from './PipelineTimeline';
import { useRunDiagnostics } from './use-run-diagnostics';
import { usePipelineSelection } from '@/components/pipeline-selection';
import { applyPipelineScope } from '@/lib/pipeline-scope';
import { buildRunStrip } from '@/lib/pipeline-run-strip';
import { groupRunEpisodes } from '@/lib/run-episodes';
import { apiDb } from '@/lib/api-query';
import { isApiConfigured } from '@/lib/api-client';

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
  // Prefer an explicit ?stage=; otherwise infer from ?node= so ledger-only and
  // topology-leaf deep links still expand the owning stage (#2627).
  const resolvedStage = stage ?? (node ? stageForDocumentKey(node) ?? undefined : undefined);
  const expandedStages = new Set<PipelineStageId>(resolvedStage ? [resolvedStage] : []);
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

/**
 * Pipeline surface. Keyed by the selected pipeline so switching pipelines resets
 * every panel, ledger and expansion (baseline is the only option today).
 */
export default function PipelineClient() {
  const { pipelineId } = usePipelineSelection();
  return <PipelineSurface key={pipelineId} />;
}

type DayLoadState = 'loading' | 'ready' | 'unavailable' | 'not-configured';

function PipelineSurface() {
  const { scope } = usePipelineSelection();
  const scopeId = scope.pipelineId;
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
  // 'unavailable' (read failed) is not 'no run': a DB outage must not look like an empty pipeline.
  const [loadState, setLoadState] = useState<DayLoadState>('loading');
  const [dayData, setDayData] = useState<PipelineDayData>({
    runRecorded: false,
    fanoutCounts: {},
    fanoutKeys: {},
    presentKeys: new Set(),
    artifacts: [],
  });

  // Node detail
  const [activeNode, setActiveNode] = useState<LaidOutNode | null>(null);
  const [activeDocumentKey, setActiveDocumentKey] = useState<string | null>(params.node ?? null);
  const [artifactLedgerOpen, setArtifactLedgerOpen] = useState(false);
  const [traceLedgerOpen, setTraceLedgerOpen] = useState(false);
  const [timelineOpen, setTimelineOpen] = useState(false);

  const diagnosticsState = useRunDiagnostics(scope);
  const episodes = useMemo(() => groupRunEpisodes(diagnosticsState.diagnostics ?? []), [diagnosticsState.diagnostics]);

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
        if (!isApiConfigured()) {
          if (!cancelled) setLoadState('not-configured');
          return;
        }

        const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

        // Independent reads — run them together instead of one round-trip at a time.
        const [datesRes, docsRes] = await Promise.all([
          // Run dates come from daily_snapshots (exactly one row per run day).
          // Deriving them from `documents` selects EVERY row (~40-60/day), and
          // the PostgREST 1000-row default cap silently truncated the oldest
          // dates out of the 30-day window.
          applyPipelineScope(apiDb.from('daily_snapshots').select('date'), 'daily_snapshots', scope)
            .gte('date', thirtyDaysAgo)
            .order('date', { ascending: false }),
          applyPipelineScope(
            apiDb.from('documents').select('document_key,title,doc_type,phase,category,segment,sector,run_type'),
            'documents',
            scope,
          ).eq('date', selectedDate),
        ]);

        if (cancelled) return;

        setLoadState(datesRes.error || docsRes.error ? 'unavailable' : 'ready');

        const uniqueDates = datesRes.data
          ? [...new Set((datesRes.data as { date: string }[]).map((r) => r.date))]
            .sort()
            .reverse()
          : [];
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

        if (docsRes.data) {
          setDayData({
            ...buildPipelineDayData(docsRes.data),
            runRecorded: uniqueDates.includes(selectedDate),
          });
        }

      } catch {
        // Degrade gracefully, but say so: an outage is not an empty pipeline.
        if (!cancelled) setLoadState('unavailable');
      } finally {
        if (!cancelled) setDayLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [selectedDate, scopeId]); // eslint-disable-line react-hooks/exhaustive-deps -- scope keyed by id

  // A '?node=digest' deep link (from Overview / the command palette, which don't
  // know today's baseline-vs-delta cadence) is a sentinel, not necessarily this
  // day's real key — derive the actual key to fetch/highlight once the day's
  // documents load, rather than storing it (avoids a setState-in-effect).
  const resolvedActiveDocumentKey = useMemo(() => {
    if (activeDocumentKey !== 'digest') return activeDocumentKey;
    return resolvePresentDigestKey(dayData) ?? activeDocumentKey;
  }, [activeDocumentKey, dayData]);

  const handleNodeActivate = useCallback((node: LaidOutNode) => {
    setArtifactLedgerOpen(false);
    setTraceLedgerOpen(false);
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

  const handleArtifactSelect = useCallback((documentKey: string) => {
    setArtifactLedgerOpen(false);
    setActiveNode(null);
    setActiveDocumentKey(documentKey);
  }, []);

  const handleTimelineSelect = useCallback((documentKey: string) => {
    setArtifactLedgerOpen(false);
    setTraceLedgerOpen(false);
    setActiveNode(null);
    setActiveDocumentKey(documentKey);
  }, []);

  const handleArtifactLedgerOpen = useCallback(() => {
    setTraceLedgerOpen(false);
    setArtifactLedgerOpen(true);
  }, []);

  const handleTraceLedgerOpen = useCallback(() => {
    setArtifactLedgerOpen(false);
    setActiveNode(null);
    setActiveDocumentKey(null);
    setTraceLedgerOpen(true);
  }, []);

  const noRunForDate = !dayLoading && loadState === 'ready' && dayData.runRecorded === false;
  const dataUnavailable = !dayLoading && (loadState === 'unavailable' || loadState === 'not-configured');
  const stripCells = useMemo(
    () => buildRunStrip({ runDates: availableDates, episodes, end: today() }),
    [availableDates, episodes],
  );

  return (
    <section
      data-testid="pipeline-workspace"
      aria-label="Daily decision pipeline"
      className="flex min-h-0 min-w-0 flex-1 flex-col bg-surface"
    >
      <header
        data-testid="pipeline-command-band"
        className="flex min-h-12 flex-wrap items-center justify-end gap-y-2 border-y border-hair bg-surface px-3 py-2 md:flex-nowrap md:px-4"
      >
        <h1 className="sr-only">Pipeline</h1>
        {dataUnavailable && (
          <p className="mr-auto font-mono text-xs text-warn" role="status" data-testid="pipeline-data-unavailable">
            {loadState === 'not-configured'
              ? 'API not configured — showing the expected pipeline.'
              : 'Run data unavailable — showing the expected pipeline.'}
          </p>
        )}
        {noRunForDate && (
          <p className="mr-auto font-mono text-xs text-ink-mute" role="status">
            No run recorded — showing the expected pipeline.
          </p>
        )}
        <Button
          type="button"
          variant="outline"
          aria-label="Open all pipeline artifacts"
          title="All artifacts"
          onClick={handleArtifactLedgerOpen}
          className="mr-1 h-9 w-9 gap-2 border-hair bg-term-bg font-mono text-xs text-ink hover:border-accent/50 hover:text-accent md:mr-2 md:w-auto md:px-3"
        >
          <Files size={15} aria-hidden />
          <span className="hidden md:inline">All artifacts</span>
          <span className="hidden tabular-nums text-ink-mute md:inline">{dayData.artifacts.length}</span>
        </Button>
        <Button
          type="button"
          variant="outline"
          aria-label="Open pipeline call trace"
          title="Call trace"
          onClick={handleTraceLedgerOpen}
          className="mr-1 h-9 w-9 gap-2 border-hair bg-term-bg font-mono text-xs text-ink hover:border-accent/50 hover:text-accent md:mr-2 md:w-auto md:px-3"
        >
          <ListTree size={15} aria-hidden />
          <span className="hidden md:inline">Call trace</span>
        </Button>
        <Button
          type="button"
          variant="outline"
          aria-label="Toggle run timeline"
          aria-pressed={timelineOpen}
          title="Run timeline"
          onClick={() => setTimelineOpen((v) => !v)}
          className="mr-1 h-9 w-9 gap-2 border-hair bg-term-bg font-mono text-xs text-ink hover:border-accent/50 hover:text-accent md:mr-2 md:w-auto md:px-3"
        >
          <ChartGantt size={15} aria-hidden />
          <span className="hidden md:inline">Timeline</span>
        </Button>
        <PipelineDaySelector
          dates={availableDates}
          value={selectedDate}
          onChange={handleDateChange}
        />
      </header>

      <PipelineRunStrip
        cells={stripCells}
        selectedDate={selectedDate}
        onSelect={handleDateChange}
        loading={diagnosticsState.loading && dayLoading}
      />

      <PipelineRunHealth
        date={selectedDate}
        scope={scope}
        state={diagnosticsState}
        artifactCount={dayData.artifacts.length}
      />

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

        {artifactLedgerOpen && (
          <PipelineArtifactLedger
            artifacts={dayData.artifacts}
            date={selectedDate}
            selectedDocumentKey={resolvedActiveDocumentKey}
            onSelect={handleArtifactSelect}
            onClose={() => setArtifactLedgerOpen(false)}
          />
        )}

        {traceLedgerOpen && (
          <PipelineTraceLedger
            date={selectedDate}
            scope={scope}
            onClose={() => setTraceLedgerOpen(false)}
          />
        )}

        {!artifactLedgerOpen && !traceLedgerOpen && resolvedActiveDocumentKey !== null && (
          <PipelineNodeDetail
            node={activeNode}
            documentKey={resolvedActiveDocumentKey}
            date={selectedDate}
            scope={scope}
            onClose={handleDetailClose}
          />
        )}
      </div>

      {timelineOpen && (
        <PipelineTimeline
          date={selectedDate}
          scope={scope}
          selectedKey={resolvedActiveDocumentKey}
          onSelectKey={handleTimelineSelect}
        />
      )}
    </section>
  );
}
