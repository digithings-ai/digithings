'use client';

import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Calendar, ChevronDown, ChevronUp } from 'lucide-react';
import MiniCalendar, { type MiniCalendarRunKind } from '@/components/library/MiniCalendar';
import type { PipelineObservabilityBundle, Thesis, ThesisHistoryPoint } from '@/lib/types';
import { fetchThesisPipelinePayloadsForDate, getThesisHistoryById } from '@/lib/queries';
import { thesisPipelineNarrativeFromPayloads } from '@/lib/thesis-pipeline-snapshot';

function pickThesisSnapshotForDate(points: ThesisHistoryPoint[], asOf: string): ThesisHistoryPoint | null {
  const eligible = points.filter((p) => p.date <= asOf);
  if (!eligible.length) return null;
  return [...eligible].sort((a, b) => b.date.localeCompare(a.date))[0];
}

export default function ThesesTab(props: {
  historyTimelineDates: string[];
  portfolioHistoryRunKindByDate: Map<string, MiniCalendarRunKind>;
  effHistoryDate: string | null;
  onSelectHistoryDate: (iso: string) => void;
  historyLatestDate: string | null;
  onClearHistoryDate: () => void;
  thesisBookRowsForHistoryDate: { id: string; thesis: Thesis | null; weight: number }[];
  lastUpdated: string | null;
  portfolioDocDates: Set<string>;
  positionHistoryDates: Set<string>;
  pipelineObservability: PipelineObservabilityBundle | null;
}) {
  const {
    historyTimelineDates,
    portfolioHistoryRunKindByDate,
    effHistoryDate,
    onSelectHistoryDate,
    historyLatestDate,
    onClearHistoryDate,
    thesisBookRowsForHistoryDate,
    lastUpdated,
    portfolioDocDates,
    positionHistoryDates,
    pipelineObservability,
  } = props;

  const selectHistoryDate = useCallback(
    (iso: string) => {
      onSelectHistoryDate(iso);
    },
    [onSelectHistoryDate]
  );

  const clearHistoryDate = useCallback(() => {
    onClearHistoryDate();
  }, [onClearHistoryDate]);

  const [expandedThesisId, setExpandedThesisId] = useState<string | null>(null);
  const [historyByThesis, setHistoryByThesis] = useState<Map<string, ThesisHistoryPoint[]>>(new Map());

  const [pipelineCacheByDate, setPipelineCacheByDate] = useState<
    Map<string, { mte: Record<string, unknown> | null; tvm: Record<string, unknown> | null }>
  >(() => new Map());
  const [pipelineLoading, setPipelineLoading] = useState(false);

  useEffect(() => {
    if (!expandedThesisId || expandedThesisId === '_unlinked') return;
    let cancelled = false;
    getThesisHistoryById(expandedThesisId).then((rows) => {
      if (!cancelled) {
        setHistoryByThesis((prev) => new Map(prev).set(expandedThesisId, rows));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [expandedThesisId]);

  useEffect(() => {
    if (!effHistoryDate || expandedThesisId === null || expandedThesisId === '_unlinked') {
      return;
    }

    const key = effHistoryDate;

    /* Latest digest day: MTE/TVM come from props in useMemo — no network. */
    if (key === lastUpdated && pipelineObservability != null) return;

    if (pipelineCacheByDate.has(key)) return;

    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) setPipelineLoading(true);
    });
    fetchThesisPipelinePayloadsForDate(key)
      .then((res) => {
        if (cancelled) return;
        setPipelineCacheByDate((prev) => {
          const next = new Map(prev);
          next.set(key, {
            mte: res.market_thesis_exploration,
            tvm: res.thesis_vehicle_map,
          });
          return next;
        });
      })
      .finally(() => {
        if (!cancelled) setPipelineLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [effHistoryDate, expandedThesisId, lastUpdated, pipelineObservability, pipelineCacheByDate]);

  const payloadsForSelectedDate = useMemo(() => {
    if (!effHistoryDate) {
      return { mte: null as Record<string, unknown> | null, tvm: null as Record<string, unknown> | null };
    }
    const hit = pipelineCacheByDate.get(effHistoryDate);
    if (hit) return hit;
    if (effHistoryDate === lastUpdated && pipelineObservability) {
      return {
        mte: pipelineObservability.market_thesis_exploration,
        tvm: pipelineObservability.thesis_vehicle_map,
      };
    }
    return { mte: null, tvm: null };
  }, [effHistoryDate, lastUpdated, pipelineObservability, pipelineCacheByDate]);

  const colCount = 6;

  return (
    <div className="flex gap-6 max-lg:flex-col">
      <div className="w-56 shrink-0 space-y-4 max-lg:w-full max-lg:flex max-lg:gap-4 max-lg:flex-wrap">
        <div className="space-y-2">
          <p className="text-[10px] font-medium text-text-muted px-0.5">History</p>
          {historyTimelineDates.length > 0 ? (
            <MiniCalendar
              dates={historyTimelineDates}
              runKindByDate={portfolioHistoryRunKindByDate}
              selected={effHistoryDate}
              onSelect={selectHistoryDate}
            />
          ) : (
            <div className="glass-card p-4 text-xs text-text-muted">No dated history yet.</div>
          )}
        </div>
        {historyLatestDate && effHistoryDate && effHistoryDate !== historyLatestDate ? (
          <button
            type="button"
            onClick={clearHistoryDate}
            className="w-full text-xs py-2 rounded-lg border border-border-subtle text-text-secondary hover:text-white hover:bg-white/[0.04] transition-colors"
          >
            Jump to latest ({historyLatestDate})
          </button>
        ) : null}
      </div>

      <div className="flex-1 min-w-0 space-y-10">
        <section className="space-y-4">
          <div className="flex items-center gap-2 px-0.5">
            <Calendar size={15} className="text-fin-blue shrink-0" aria-hidden />
            <span className="text-xs font-medium text-text-muted font-mono">{effHistoryDate ?? '—'}</span>
            {effHistoryDate &&
            !portfolioDocDates.has(effHistoryDate) &&
            positionHistoryDates.has(effHistoryDate) ? (
              <span className="text-xs text-text-muted ml-2">
                No portfolio documents indexed for this date; weights use position history.
              </span>
            ) : null}
          </div>

          <div className="space-y-4">
            {effHistoryDate && lastUpdated && effHistoryDate !== lastUpdated ? (
              <p className="text-xs text-text-muted px-1">
                Weights as of <span className="font-mono text-text-secondary">{effHistoryDate}</span>. Thesis
                text from digest <span className="font-mono text-text-secondary">{lastUpdated}</span>.
              </p>
            ) : null}

            <div className="glass-card p-0 overflow-hidden">
              <div className="px-5 py-4 border-b border-border-subtle bg-bg-secondary flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold">Theses</h3>
                  <p className="text-xs text-text-muted mt-0.5 font-mono">{effHistoryDate ?? '—'}</p>
                </div>
                <p className="text-[11px] text-text-muted">
                  Expand for DB snapshots, pipeline narrative, and history
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-0 text-sm md:min-w-[640px]">
                  <thead>
                    <tr className="border-b border-border-subtle text-xs uppercase tracking-wider text-text-muted">
                      <th className="px-4 py-3 text-left md:px-5">Thesis</th>
                      <th className="px-4 py-3 text-right md:px-5">Weight</th>
                      <th className="hidden px-5 py-3 text-left md:table-cell">Vehicle</th>
                      <th className="px-4 py-3 text-left md:px-5">Status</th>
                      <th className="hidden px-5 py-3 text-left lg:table-cell">Invalidation</th>
                      <th className="w-10 px-2 py-3 md:px-3" aria-hidden />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {thesisBookRowsForHistoryDate.map((row) => {
                      const label =
                        row.id === '_unlinked' ? 'Unlinked positions' : row.thesis?.name ?? row.id;
                      const status = row.thesis?.status?.toLowerCase() ?? '';
                      const statusAccent =
                        status.includes('active') || status.includes('open')
                          ? 'border-l-2 border-l-fin-green/70'
                          : status.includes('watch') || status.includes('monitor')
                            ? 'border-l-2 border-l-fin-amber/70'
                            : status.includes('invalid') || status.includes('exit') || status.includes('closed')
                              ? 'border-l-2 border-l-fin-red/70'
                              : row.id === '_unlinked'
                                ? 'border-l-2 border-l-white/10'
                                : 'border-l-2 border-l-transparent';
                      const isOpen = expandedThesisId === row.id;
                      const pipe =
                        row.id !== '_unlinked'
                          ? thesisPipelineNarrativeFromPayloads(
                              row.id,
                              payloadsForSelectedDate.mte,
                              payloadsForSelectedDate.tvm
                            )
                          : { exploration: null, vehicles: null };
                      const hist = row.id !== '_unlinked' ? historyByThesis.get(row.id) : undefined;
                      const snap =
                        effHistoryDate && hist?.length
                          ? pickThesisSnapshotForDate(hist, effHistoryDate)
                          : null;
                      const historySorted =
                        hist && hist.length
                          ? [...hist].sort((a, b) => b.date.localeCompare(a.date))
                          : [];

                      return (
                        <Fragment key={row.id}>
                          <tr
                            role="button"
                            tabIndex={0}
                            onClick={() => setExpandedThesisId(isOpen ? null : row.id)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                setExpandedThesisId(isOpen ? null : row.id);
                              }
                            }}
                            className={`hover:bg-white/[0.02] cursor-pointer transition-colors ${statusAccent}`}
                          >
                            <td className="px-4 py-3 font-medium md:px-5">{label}</td>
                            <td className="px-4 py-3 text-right font-mono font-semibold tabular-nums md:px-5">
                              {row.weight.toFixed(1)}%
                            </td>
                            <td className="hidden px-5 py-3 font-mono text-xs text-text-secondary md:table-cell">
                              {row.thesis?.vehicle ?? '—'}
                            </td>
                            <td className="px-4 py-3 text-xs text-text-secondary md:px-5">
                              {row.thesis?.status ?? '—'}
                            </td>
                            <td
                              className="hidden max-w-[200px] truncate px-5 py-3 text-xs text-text-muted lg:table-cell"
                              title={row.thesis?.invalidation ?? undefined}
                            >
                              {row.thesis?.invalidation ?? '—'}
                            </td>
                            <td className="px-2 py-3 text-text-muted md:px-3">
                              {isOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                            </td>
                          </tr>
                          {isOpen && (
                            <tr className="bg-white/[0.02]">
                              <td colSpan={colCount} className="px-4 py-5 md:px-6 md:py-6">
                                {row.id === '_unlinked' ? (
                                  <p className="text-sm text-text-secondary max-w-3xl leading-relaxed">
                                    Holdings not linked to a named thesis in position history. Link positions to a
                                    thesis in the book snapshot to roll them up under a thesis sleeve.
                                  </p>
                                ) : (
                                  <div className="space-y-4 max-w-4xl">
                                    <div className="grid gap-4 md:grid-cols-2">
                                      <div className="rounded-xl border border-border-subtle bg-bg-secondary/40 p-4 space-y-2">
                                        <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">
                                          Book snapshot ({effHistoryDate ?? '—'})
                                        </p>
                                        {snap ? (
                                          <>
                                            <p className="text-xs font-mono text-text-muted">{snap.date}</p>
                                            <p className="text-sm text-text-secondary">
                                              <span className="text-text-muted">Status:</span> {snap.status ?? '—'}
                                            </p>
                                            {snap.notes ? (
                                              <p className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">
                                                {snap.notes}
                                              </p>
                                            ) : (
                                              <p className="text-xs text-text-muted">No notes on this snapshot.</p>
                                            )}
                                          </>
                                        ) : (
                                          <p className="text-xs text-text-muted">
                                            No thesis row in the database on or before this date.
                                          </p>
                                        )}
                                      </div>
                                      <div className="rounded-xl border border-border-subtle bg-bg-secondary/40 p-4 space-y-2">
                                        <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">
                                          Current strategy (latest digest)
                                        </p>
                                        {row.thesis?.notes ? (
                                          <p className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">
                                            {row.thesis.notes}
                                          </p>
                                        ) : (
                                          <p className="text-xs text-text-muted">No summary in latest strategy.</p>
                                        )}
                                      </div>
                                    </div>

                                    {historySorted.length > 0 && (
                                      <div className="rounded-xl border border-border-subtle bg-bg-secondary/20 overflow-hidden">
                                        <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider px-4 pt-3 pb-2">
                                          Thesis record over time (database)
                                        </p>
                                        <div className="overflow-x-auto max-h-[260px] overflow-y-auto">
                                          <table className="w-full text-xs">
                                            <thead className="sticky top-0 bg-bg-secondary/95 z-[1] border-b border-border-subtle">
                                              <tr className="text-left text-text-muted uppercase tracking-wider">
                                                <th className="px-4 py-2 font-medium">Date</th>
                                                <th className="px-4 py-2 font-medium">Name</th>
                                                <th className="px-4 py-2 font-medium">Status</th>
                                                <th className="px-4 py-2 font-medium min-w-[200px]">Notes</th>
                                              </tr>
                                            </thead>
                                            <tbody className="divide-y divide-border-subtle text-text-secondary">
                                              {historySorted.map((h) => (
                                                <tr key={`${h.date}-${h.thesis_id}`}>
                                                  <td className="px-4 py-2 font-mono whitespace-nowrap align-top">
                                                    {h.date}
                                                  </td>
                                                  <td className="px-4 py-2 align-top">{h.name}</td>
                                                  <td className="px-4 py-2 align-top whitespace-nowrap">
                                                    {h.status ?? '—'}
                                                  </td>
                                                  <td className="px-4 py-2 text-text-muted align-top whitespace-pre-wrap max-w-xl">
                                                    {h.notes ?? '—'}
                                                  </td>
                                                </tr>
                                              ))}
                                            </tbody>
                                          </table>
                                        </div>
                                      </div>
                                    )}

                                    {isOpen &&
                                    pipelineLoading &&
                                    effHistoryDate &&
                                    !pipelineCacheByDate.has(effHistoryDate) &&
                                    !(effHistoryDate === lastUpdated && pipelineObservability != null) ? (
                                      <p className="text-xs text-text-muted animate-pulse">
                                        Loading thesis exploration & vehicle map for{' '}
                                        <span className="font-mono">{effHistoryDate}</span>…
                                      </p>
                                    ) : null}

                                    {(pipe.exploration || pipe.vehicles) && (
                                      <div className="rounded-xl border border-fin-blue/20 bg-fin-blue/5 p-4 space-y-3">
                                        <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">
                                          Pipeline — market thesis exploration & vehicle map (
                                          <span className="font-mono">{effHistoryDate ?? '—'}</span>)
                                        </p>
                                        {pipe.exploration ? (
                                          <div>
                                            <p className="text-xs font-medium text-text-secondary mb-1">
                                              Market thesis exploration
                                            </p>
                                            <p className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">
                                              {pipe.exploration}
                                            </p>
                                          </div>
                                        ) : null}
                                        {pipe.vehicles ? (
                                          <div>
                                            <p className="text-xs font-medium text-text-secondary mb-1">
                                              Thesis vehicle map
                                            </p>
                                            <p className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">
                                              {pipe.vehicles}
                                            </p>
                                          </div>
                                        ) : null}
                                      </div>
                                    )}

                                    {effHistoryDate &&
                                    !pipelineLoading &&
                                    !pipe.exploration &&
                                    !pipe.vehicles &&
                                    (effHistoryDate !== lastUpdated ||
                                      (effHistoryDate === lastUpdated && !pipelineObservability)) && (
                                      <p className="text-xs text-text-muted">
                                        No thesis exploration or vehicle map JSON in the library for{' '}
                                        <span className="font-mono">{effHistoryDate}</span>. Open{' '}
                                        <Link
                                          href={`/portfolio?tab=analysis&date=${encodeURIComponent(effHistoryDate)}`}
                                          className="text-fin-blue hover:underline"
                                        >
                                          Intelligence
                                        </Link>{' '}
                                        or Research for that run.
                                      </p>
                                    )}
                                  </div>
                                )}
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                    {thesisBookRowsForHistoryDate.length === 0 && (
                      <tr>
                        <td colSpan={colCount} className="text-center py-8 text-text-muted">
                          No theses in latest snapshot
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
