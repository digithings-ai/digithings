'use client';

import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  ChevronDown,
  Clock3,
  Globe2,
  Search,
  Wrench,
  X,
} from 'lucide-react';
import { fetchPipelineTrace } from '@/lib/pipeline-trace';
import type {
  PipelineRunEvent,
  PipelineTraceResult,
} from '@/lib/pipeline-trace';
import {
  TRACE_UI_PAGE_SIZE,
  classifyTraceStageEmpty,
  filterPipelineTraceByStage,
  nextTracePageLimit,
  paginatePipelineTraceEvents,
  pipelineStageFilters,
  traceStageLabel,
  type TraceStageFilter,
} from '@/lib/pipeline-trace-stage';

type KindFilter = 'all' | PipelineRunEvent['event_kind'];
type AttentionFilter = 'all' | 'issues';

function normalizedSearchText(event: PipelineRunEvent): string {
  return [
    event.run_id,
    event.run_type,
    event.event_kind,
    event.phase,
    event.operation,
    event.document_key,
    event.name,
    event.status,
    event.input_summary,
    event.output_summary,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

export function filterPipelineTraceEvents(
  events: PipelineRunEvent[],
  query: string,
  kind: KindFilter,
  attention: AttentionFilter,
  stage: TraceStageFilter = 'all',
): PipelineRunEvent[] {
  const normalizedQuery = query.trim().toLowerCase();
  return filterPipelineTraceByStage(events, stage).filter((event) => {
    if (kind !== 'all' && event.event_kind !== kind) return false;
    if (attention === 'issues' && event.status !== 'error' && event.retry_count === 0) {
      return false;
    }
    return normalizedQuery.length === 0 || normalizedSearchText(event).includes(normalizedQuery);
  });
}

interface PhaseGroup {
  key: string;
  label: string;
  events: PipelineRunEvent[];
}

interface AttemptGroup {
  key: string;
  runId: string;
  attempt: number;
  runType: string | null;
  phases: PhaseGroup[];
}

export function groupPipelineTraceEvents(events: PipelineRunEvent[]): AttemptGroup[] {
  const attempts = new Map<string, AttemptGroup>();
  for (const event of events) {
    const attemptKey = `${event.run_id}:${event.attempt}`;
    let attempt = attempts.get(attemptKey);
    if (!attempt) {
      attempt = {
        key: attemptKey,
        runId: event.run_id,
        attempt: event.attempt,
        runType: event.run_type,
        phases: [],
      };
      attempts.set(attemptKey, attempt);
    }

    const phaseKey = event.phase || 'unscoped';
    let phase = attempt.phases.find((item) => item.key === phaseKey);
    if (!phase) {
      phase = { key: phaseKey, label: event.phase || 'Unscoped calls', events: [] };
      attempt.phases.push(phase);
    }
    phase.events.push(event);
  }
  return [...attempts.values()];
}

function formatDuration(durationMs: number | null): string {
  if (durationMs == null) return 'Timing unavailable';
  if (durationMs < 1_000) return `${durationMs} ms`;
  if (durationMs < 60_000) return `${(durationMs / 1_000).toFixed(1)} s`;
  const minutes = Math.floor(durationMs / 60_000);
  const seconds = Math.round((durationMs % 60_000) / 1_000);
  return `${minutes}m ${seconds}s`;
}

function eventTitle(event: PipelineRunEvent): string {
  return event.operation?.trim() || event.name;
}

function EventKindIcon({ kind }: { kind: PipelineRunEvent['event_kind'] }) {
  if (kind === 'search_call') return <Globe2 size={15} aria-hidden />;
  if (kind === 'tool_call') return <Wrench size={15} aria-hidden />;
  return <Bot size={15} aria-hidden />;
}

function EmptyTrace({ state, date }: { state: Exclude<PipelineTraceResult['state'], 'available'>; date: string }) {
  const unavailable = state === 'unavailable';
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-12 text-center">
      <div className="max-w-md">
        {unavailable ? (
          <AlertTriangle size={22} aria-hidden className="mx-auto mb-3 text-warn" />
        ) : (
          <Clock3 size={22} aria-hidden className="mx-auto mb-3 text-ink-mute" />
        )}
        <h3 className="font-display text-lg text-ink">
          {unavailable ? 'Call trace unavailable' : 'No recorded call trace'}
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-ink-mute" role="status">
          {unavailable
            ? `Call trace could not be loaded for ${date}.`
            : 'Call details were not recorded for this run.'}
        </p>
      </div>
    </div>
  );
}

function TraceEvent({ event }: { event: PipelineRunEvent }) {
  const needsAttention = event.status === 'error' || event.retry_count > 0;
  return (
    <details
      data-testid="pipeline-trace-event"
      open={needsAttention || undefined}
      className={`group border-b border-hair last:border-b-0 ${
        event.status === 'error' ? 'bg-down/[0.04]' : needsAttention ? 'bg-warn/[0.04]' : ''
      }`}
    >
      <summary className="grid min-h-14 cursor-pointer list-none grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-2 py-2.5 marker:hidden hover:bg-accent/[0.03] md:grid-cols-[3.25rem_auto_minmax(0,1fr)_auto] md:px-3">
        <span className="hidden font-mono text-[0.65rem] tabular-nums text-ink-mute md:block">
          #{String(event.sequence).padStart(3, '0')}
        </span>
        <span
          title={event.event_kind.replace('_', ' ')}
          className={`flex h-8 w-8 items-center justify-center rounded-md border ${
            event.status === 'error'
              ? 'border-down/30 text-down'
              : needsAttention
                ? 'border-warn/30 text-warn'
                : 'border-hair text-accent'
          }`}
        >
          <EventKindIcon kind={event.event_kind} />
        </span>
        <span className="min-w-0">
          <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="truncate text-sm font-medium text-ink">{eventTitle(event)}</span>
            <span className="font-mono text-[0.65rem] text-ink-mute md:hidden">
              #{event.sequence}
            </span>
          </span>
          <span className="mt-0.5 block truncate font-mono text-[0.65rem] text-ink-mute">
            {event.name}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {event.status === 'error' ? (
            <span className="font-mono text-[0.62rem] font-semibold uppercase text-down">Error</span>
          ) : event.retry_count > 0 ? (
            <span className="font-mono text-[0.62rem] font-semibold uppercase text-warn">
              {event.retry_count} {event.retry_count === 1 ? 'retry' : 'retries'}
            </span>
          ) : null}
          <span className="hidden font-mono text-[0.65rem] tabular-nums text-ink-mute sm:block">
            {formatDuration(event.duration_ms)}
          </span>
          <ChevronDown
            size={14}
            aria-hidden
            className="text-ink-mute transition-transform group-open:rotate-180"
          />
        </span>
      </summary>

      <div className="grid gap-x-6 gap-y-3 border-t border-hair/70 bg-surface/50 px-4 py-3 text-xs md:grid-cols-2 md:px-[4.75rem]">
        <div>
          <span className="block font-mono text-[0.62rem] font-semibold uppercase text-ink-mute">
            Input
          </span>
          <p className="mt-1 break-words leading-relaxed text-ink">{event.input_summary}</p>
        </div>
        <div>
          <span className="block font-mono text-[0.62rem] font-semibold uppercase text-ink-mute">
            Output
          </span>
          <p className="mt-1 break-words leading-relaxed text-ink">{event.output_summary}</p>
        </div>
        <div className="font-mono text-[0.68rem] leading-relaxed text-ink-mute">
          <span className="sm:hidden">{formatDuration(event.duration_ms)} · </span>
          {event.sources > 0 ? `${event.sources} sources · ` : ''}
          {event.status === 'ok' ? 'Completed' : 'Failed'}
        </div>
        {event.document_key ? (
          <div className="break-all text-right font-mono text-[0.68rem] text-ink-mute">
            {event.document_key}
          </div>
        ) : null}
      </div>
    </details>
  );
}

export function PipelineTraceView({
  result,
  date,
  onClose,
}: {
  result: PipelineTraceResult;
  date: string;
  onClose: () => void;
}) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<KindFilter>('all');
  const [attention, setAttention] = useState<AttentionFilter>('all');
  const [stage, setStage] = useState<TraceStageFilter>('all');
  const [pagination, setPagination] = useState({ key: '', limit: TRACE_UI_PAGE_SIZE });
  const deferredQuery = useDeferredValue(query);
  const events = result.events;
  const filtered = useMemo(
    () => filterPipelineTraceEvents(events, deferredQuery, kind, attention, stage),
    [attention, deferredQuery, events, kind, stage],
  );
  const filterKey = `${deferredQuery.trim().toLowerCase()}|${kind}|${attention}|${stage}`;
  const visibleLimit = pagination.key === filterKey ? pagination.limit : TRACE_UI_PAGE_SIZE;
  const visibleEvents = paginatePipelineTraceEvents(filtered, visibleLimit);
  const groups = useMemo(() => groupPipelineTraceEvents(visibleEvents), [visibleEvents]);
  const errors = events.filter((event) => event.status === 'error').length;
  const retries = events.reduce((total, event) => total + event.retry_count, 0);
  const remaining = Math.max(0, filtered.length - visibleEvents.length);
  const stageEmpty = classifyTraceStageEmpty(stage, events.length);

  return (
    <aside
      aria-label="Pipeline call trace"
      className="fixed inset-0 z-[1050] flex h-dvh w-full flex-col overflow-hidden bg-term-bg pt-[env(safe-area-inset-top)] md:relative md:inset-auto md:z-20 md:h-full md:min-h-0 md:w-[min(78vw,1040px)] md:border-l md:border-hair md:pt-0"
    >
      <header className="flex items-start justify-between gap-3 border-b border-hair px-4 py-3 md:px-5 md:py-4">
        <div className="min-w-0">
          <h2 className="font-display text-xl text-ink">Call trace</h2>
          <p className="mt-0.5 font-mono text-xs text-ink-mute">
            {events.length} calls · {date}
            {retries > 0 ? ` · ${retries} retries` : ''}
            {errors > 0 ? ` · ${errors} errors` : ''}
            {stage !== 'all' ? ` · ${traceStageLabel(stage)}` : ''}
          </p>
        </div>
        <button
          type="button"
          aria-label="Close call trace"
          onClick={onClose}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-hair text-ink-mute transition-colors hover:text-ink md:h-8 md:w-8"
        >
          <X size={18} aria-hidden />
        </button>
      </header>

      {result.state !== 'available' ? (
        <EmptyTrace state={result.state} date={date} />
      ) : (
        <>
          <div className="space-y-3 border-b border-hair px-3 py-3 md:px-5">
            <label className="relative block">
              <span className="sr-only">Search call trace</span>
              <Search
                size={15}
                aria-hidden
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-mute"
              />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search phases, operations, models, tools, or artifacts"
                className="h-10 w-full rounded-lg border border-hair bg-surface pl-9 pr-3 font-mono text-xs text-ink outline-none transition-colors placeholder:text-ink-mute/70 focus:border-accent"
              />
            </label>
            <div
              className="flex flex-wrap gap-1"
              aria-label="Pipeline stage filter"
            >
              {pipelineStageFilters().map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={stage === value}
                  onClick={() => setStage(value)}
                  className={`h-8 rounded-md border px-2.5 font-mono text-[0.62rem] transition-colors ${
                    stage === value
                      ? 'border-accent/40 bg-accent/10 text-accent'
                      : 'border-hair text-ink-mute hover:text-ink'
                  }`}
                >
                  {value === 'all' ? 'All stages' : traceStageLabel(value)}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="inline-flex rounded-lg border border-hair bg-surface p-0.5" aria-label="Call type filter">
                {([
                  ['all', 'All'],
                  ['model_call', 'Models'],
                  ['search_call', 'Search'],
                  ['tool_call', 'Tools'],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={kind === value}
                    onClick={() => setKind(value)}
                    className={`h-8 px-2.5 font-mono text-[0.65rem] transition-colors ${
                      kind === value ? 'rounded-md bg-accent/10 text-accent' : 'text-ink-mute hover:text-ink'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                aria-pressed={attention === 'issues'}
                onClick={() => setAttention(attention === 'issues' ? 'all' : 'issues')}
                className={`inline-flex h-9 items-center gap-2 rounded-lg border px-3 font-mono text-[0.65rem] transition-colors ${
                  attention === 'issues'
                    ? 'border-warn/40 bg-warn/[0.08] text-warn'
                    : 'border-hair text-ink-mute hover:text-ink'
                }`}
              >
                <AlertTriangle size={13} aria-hidden />
                Retries & errors
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto overscroll-contain px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] md:px-5">
            {groups.length > 0 ? (
              groups.map((attempt) => (
                <section key={attempt.key} className="mb-6 last:mb-0">
                  <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2 border-b border-hair pb-2">
                    <div className="min-w-0">
                      <h3 className="truncate font-mono text-xs font-semibold text-ink">
                        {attempt.runId}
                      </h3>
                      <p className="mt-0.5 font-mono text-[0.62rem] uppercase text-ink-mute">
                        Attempt {attempt.attempt}{attempt.runType ? ` · ${attempt.runType}` : ''}
                      </p>
                    </div>
                    <span className="font-mono text-xs tabular-nums text-ink-mute">
                      {attempt.phases.reduce((count, phase) => count + phase.events.length, 0)} calls
                    </span>
                  </div>

                  {attempt.phases.map((phase) => (
                    <section key={`${attempt.key}:${phase.key}`} className="mb-4 last:mb-0">
                      <div className="mb-1.5 flex items-center justify-between gap-3 px-2">
                        <h4 className="truncate font-mono text-[0.66rem] font-semibold uppercase text-ink-mute">
                          {phase.label}
                        </h4>
                        <span className="font-mono text-[0.65rem] tabular-nums text-ink-mute">
                          {phase.events.length}
                        </span>
                      </div>
                      <div className="border-y border-hair">
                        {phase.events.map((event) => (
                          <TraceEvent
                            key={`${event.run_id}:${event.attempt}:${event.sequence}`}
                            event={event}
                          />
                        ))}
                      </div>
                    </section>
                  ))}
                </section>
              ))
            ) : stageEmpty === 'typed-gap' && stage !== 'all' ? (
              <div className="py-8 text-center">
                <AlertTriangle size={20} aria-hidden className="mx-auto mb-3 text-warn" />
                <p className="text-sm text-ink" role="status">
                  No call telemetry for {traceStageLabel(stage)}
                </p>
                <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-ink-mute">
                  This stage is a typed persistence gap: the graph does not emit model, search, or
                  tool call rows for it. Call trace will not invent operations here.
                </p>
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-ink-mute">
                No calls match the current filters.
              </p>
            )}

            {remaining > 0 ? (
              <div className="flex justify-center border-t border-hair pt-4">
                <button
                  type="button"
                  onClick={() =>
                    setPagination({
                      key: filterKey,
                      limit: nextTracePageLimit(visibleLimit, filtered.length),
                    })
                  }
                  className="h-9 rounded-lg border border-hair px-4 font-mono text-xs text-ink transition-colors hover:border-accent/50 hover:text-accent"
                >
                  Load {Math.min(TRACE_UI_PAGE_SIZE, remaining)} more · {remaining} remaining
                </button>
              </div>
            ) : null}
          </div>
        </>
      )}
    </aside>
  );
}

export default function PipelineTraceLedger({
  date,
  onClose,
}: {
  date: string;
  onClose: () => void;
}) {
  const [loaded, setLoaded] = useState<{ date: string; result: PipelineTraceResult } | null>(null);
  const result = loaded?.date === date ? loaded.result : null;

  useEffect(() => {
    let cancelled = false;
    void fetchPipelineTrace(date).then((nextResult) => {
      if (!cancelled) setLoaded({ date, result: nextResult });
    });
    return () => {
      cancelled = true;
    };
  }, [date]);

  if (result === null) {
    return (
      <aside
        aria-label="Pipeline call trace"
        aria-busy="true"
        className="fixed inset-0 z-[1050] flex h-dvh w-full flex-col bg-term-bg pt-[env(safe-area-inset-top)] md:relative md:inset-auto md:z-20 md:h-full md:w-[min(78vw,1040px)] md:border-l md:border-hair md:pt-0"
      >
        <header className="flex items-center justify-between border-b border-hair px-4 py-3 md:px-5 md:py-4">
          <div>
            <h2 className="font-display text-xl text-ink">Call trace</h2>
            <p className="mt-0.5 font-mono text-xs text-ink-mute">Loading · {date}</p>
          </div>
          <button
            type="button"
            aria-label="Close call trace"
            onClick={onClose}
            className="flex h-11 w-11 items-center justify-center rounded-lg border border-hair text-ink-mute md:h-8 md:w-8"
          >
            <X size={18} aria-hidden />
          </button>
        </header>
        <p className="m-auto font-mono text-xs text-ink-mute" role="status">Loading call trace…</p>
      </aside>
    );
  }

  return <PipelineTraceView result={result} date={date} onClose={onClose} />;
}
