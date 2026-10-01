'use client';

import { useEffect, useMemo, useState } from 'react';
import { EmptyState, Skeleton, WaterfallTrace } from '@digithings/ui/ui';
import { fetchPipelineTrace, type PipelineTraceResult } from '@/lib/pipeline-trace';
import { buildPipelineTimeline, formatMs, timelineCallsLabel } from '@/lib/pipeline-timeline';
import type { PipelineScope } from '@/lib/pipelines';

export interface PipelineTimelineViewProps {
  result: PipelineTraceResult;
  selectedKey?: string | null;
  onSelectKey?: (documentKey: string) => void;
}

/** Waterfall of the day's calls by stage. Pure view over a trace result (testable without fetching). */
export function PipelineTimelineView({ result, selectedKey, onSelectKey }: PipelineTimelineViewProps) {
  const timeline = useMemo(() => buildPipelineTimeline(result.events), [result]);

  if (result.state === 'unavailable') {
    return (
      <EmptyState
        dress="glass"
        variant="error"
        title="Call trace unavailable"
        body="The run event trace could not be read, so no timeline is drawn. This is not the same as a run with no calls."
      />
    );
  }
  if (result.state === 'not-recorded') {
    return (
      <EmptyState
        dress="glass"
        title="No calls recorded"
        body="No call trace exists for this date. Stages that emit no calls are labelled on the timeline once a trace is recorded."
      />
    );
  }

  const selectedId = selectedKey
    ? Object.entries(timeline.keyById).find(([, k]) => k === selectedKey)?.[0] ?? null
    : null;

  return (
    <div data-testid="pipeline-timeline-view" className="space-y-2">
      <p className="font-mono text-[0.65rem] text-ink-mute">
        {timelineCallsLabel(timeline)} · {formatMs(timeline.totalMs)} span · {timeline.retries} retries · {timeline.errors} errors
        {timeline.basis === 'sequence' ? ' · ordered by sequence (no timestamps)' : ''}
        {timeline.unmapped > 0 ? ` · ${timeline.unmapped} not mapped to a stage` : ''}
      </p>
      <WaterfallTrace
        rows={timeline.rows}
        total={timeline.totalMs}
        formatDuration={formatMs}
        selectedId={selectedId}
        onSelect={(id) => {
          const key = timeline.keyById[id];
          if (key && onSelectKey) onSelectKey(key);
        }}
        label="Pipeline call timeline by stage"
        emptyLabel="No spans to show."
      />
    </div>
  );
}

/** Dock content: loads the trace only when mounted (the dock is opt-in). */
export default function PipelineTimeline({
  date,
  scope,
  selectedKey,
  onSelectKey,
}: {
  date: string;
  scope?: PipelineScope;
  selectedKey?: string | null;
  onSelectKey?: (documentKey: string) => void;
}) {
  const [loaded, setLoaded] = useState<{ date: string; pipelineId?: string; result: PipelineTraceResult } | null>(null);
  const pipelineId = scope?.pipelineId;

  useEffect(() => {
    let cancelled = false;
    void fetchPipelineTrace(date, pipelineId ? { pipelineId } : undefined).then((result) => {
      if (!cancelled) setLoaded({ date, pipelineId, result });
    });
    return () => {
      cancelled = true;
    };
  }, [date, pipelineId]);

  const current = loaded && loaded.date === date && loaded.pipelineId === pipelineId ? loaded.result : null;

  return (
    <section
      data-testid="pipeline-timeline"
      aria-label="Pipeline run timeline"
      className="max-h-72 overflow-y-auto border-t border-hair bg-surface px-3 py-3 md:px-4"
    >
      <h2 className="mb-2 font-mono text-[0.62rem] font-semibold uppercase tracking-[0.1em] text-ink-mute">
        Run timeline · {date}
      </h2>
      {current === null ? (
        <div aria-busy="true" role="status" aria-label="Loading call timeline">
          <Skeleton variant="block" className="h-24 w-full" />
        </div>
      ) : (
        <PipelineTimelineView result={current} selectedKey={selectedKey} onSelectKey={onSelectKey} />
      )}
    </section>
  );
}
