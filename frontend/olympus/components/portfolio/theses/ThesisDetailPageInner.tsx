'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  aggregateThesisWeightsByDate,
  aggregateUnlinkedWeightsByDate,
  collectThesisRelatedDocLinks,
  getThesisHistoryById,
} from '@/lib/queries';
import type { ThesisHistoryPoint } from '@/lib/types';
import { useDashboard } from '@/lib/dashboard-context';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import AtlasLoader from '@/components/AtlasLoader';
import { ArrowLeft } from 'lucide-react';

export default function ThesisDetailPageInner({ thesisId }: { thesisId: string }) {
  const { data, loading, error } = useDashboard();
  const [history, setHistory] = useState<ThesisHistoryPoint[]>([]);
  const [historyLoading, setHistoryLoading] = useState(
    () => Boolean(thesisId) && thesisId !== '_unlinked'
  );

  const theses = useMemo(() => data?.portfolio?.strategy?.theses ?? [], [data]);
  const thesis = useMemo(() => (thesisId === '_unlinked' ? null : theses.find((t) => t.id === thesisId) ?? null), [theses, thesisId]);
  const positionHistory = useMemo(() => data?.position_history ?? [], [data]);
  const positionEvents = useMemo(() => data?.position_events ?? [], [data]);
  const lastUpdated = data?.portfolio?.meta?.last_updated ?? null;
  const docs = data?.docs;

  useEffect(() => {
    if (!thesisId || thesisId === '_unlinked') return;
    let cancelled = false;
    getThesisHistoryById(thesisId)
      .then((rows) => {
        if (!cancelled) setHistory(rows);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [thesisId]);

  const weightSeries = useMemo(() => {
    if (thesisId === '_unlinked') return aggregateUnlinkedWeightsByDate(positionHistory);
    return aggregateThesisWeightsByDate(positionHistory, thesisId);
  }, [positionHistory, thesisId]);

  const latestHistoryDate = useMemo(() => {
    const rows = positionHistory.filter((r) =>
      thesisId === '_unlinked' ? !r.thesis_id : r.thesis_id === thesisId
    );
    if (!rows.length) return null;
    return [...new Set(rows.map((r) => r.date))].sort().reverse()[0] ?? null;
  }, [positionHistory, thesisId]);

  const tickersOnLatest = useMemo(() => {
    if (!latestHistoryDate) return new Set<string>();
    const s = new Set<string>();
    for (const r of positionHistory) {
      if (r.date !== latestHistoryDate) continue;
      if (thesisId === '_unlinked') {
        if (!r.thesis_id) s.add(r.ticker);
      } else if (r.thesis_id === thesisId) {
        s.add(r.ticker);
      }
    }
    return s;
  }, [positionHistory, latestHistoryDate, thesisId]);

  const recentDates = useMemo(() => {
    const d = [...new Set(positionHistory.map((r) => r.date))].sort().reverse().slice(0, 45);
    return d;
  }, [positionHistory]);

  const relatedDocs = useMemo(() => {
    if (thesisId === '_unlinked') return [];
    return collectThesisRelatedDocLinks(docs, {
      tickers: tickersOnLatest,
      recentDates,
    });
  }, [docs, thesisId, tickersOnLatest, recentDates]);

  const eventsForTickers = useMemo(() => {
    const tix = tickersOnLatest;
    if (tix.size === 0) return [];
    return positionEvents
      .filter((e) => tix.has(e.ticker))
      .sort((a, b) => b.date.localeCompare(a.date))
      .slice(0, 40);
  }, [positionEvents, tickersOnLatest]);

  if (loading) return <AtlasLoader />;
  if (error || !data)
    return (
      <div className="flex items-center justify-center min-h-[40vh] text-fin-red">
        {error || 'Failed to load'}
      </div>
    );

  if (thesisId !== '_unlinked' && !thesis) {
    return (
      <div className="flex min-h-full flex-col">
        <PortfolioSectionNav active="theses" />
        <div className={`${SUBPAGE_MAX} py-8 space-y-4`}>
          <Link
            href="/portfolio/theses"
            className="inline-flex items-center gap-2 text-sm text-fin-blue hover:underline"
          >
            <ArrowLeft size={16} /> Back to Theses
          </Link>
          <p className="text-text-muted">No thesis found for <span className="font-mono">{thesisId}</span>.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="theses" />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-8 py-4 md:py-6`}>
        <div>
          <Link
            href="/portfolio/theses"
            className="inline-flex items-center gap-2 text-sm text-fin-blue hover:underline mb-4"
          >
            <ArrowLeft size={16} /> Back to Theses
          </Link>

          {thesisId === '_unlinked' ? (
            <div className="space-y-3">
              <h1 className="text-xl font-semibold">Unlinked positions</h1>
              <p className="text-text-secondary text-sm max-w-2xl leading-relaxed">
                These holdings are not linked to a named thesis in position history. Link positions to a thesis in
                the book snapshot to see them roll up under a thesis sleeve.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <h1 className="text-xl font-semibold">{thesis?.name ?? thesisId}</h1>
              <p className="text-xs font-mono text-text-muted">{thesisId}</p>
              <div className="flex flex-wrap gap-4 text-sm text-text-secondary mt-4">
                <span>
                  <span className="text-text-muted">Status:</span> {thesis?.status ?? '—'}
                </span>
                <span>
                  <span className="text-text-muted">Vehicle:</span> {thesis?.vehicle ?? '—'}
                </span>
                <span>
                  <span className="text-text-muted">As of:</span>{' '}
                  <span className="font-mono">{lastUpdated ?? '—'}</span>
                </span>
              </div>
              {thesis?.invalidation ? (
                <p className="text-sm text-text-secondary mt-3 max-w-3xl">
                  <span className="text-text-muted">Invalidation:</span> {thesis.invalidation}
                </p>
              ) : null}
              {thesis?.notes ? (
                <div className="mt-4 rounded-xl border border-border-subtle bg-bg-secondary/40 p-4">
                  <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-2">Summary</p>
                  <p className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">{thesis.notes}</p>
                </div>
              ) : null}
            </div>
          )}
        </div>

        {thesisId !== '_unlinked' && (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Thesis record (snapshots)</h2>
            {historyLoading ? (
              <p className="text-sm text-text-muted">Loading history…</p>
            ) : history.length === 0 ? (
              <p className="text-sm text-text-muted">No historical thesis rows in the database for this id.</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-border-subtle">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border-subtle text-left text-xs text-text-muted uppercase tracking-wider">
                      <th className="px-4 py-2">Date</th>
                      <th className="px-4 py-2">Name</th>
                      <th className="px-4 py-2">Status</th>
                      <th className="px-4 py-2">Notes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {history.map((row) => (
                      <tr key={`${row.date}-${row.thesis_id}`}>
                        <td className="px-4 py-2 font-mono text-xs">{row.date}</td>
                        <td className="px-4 py-2">{row.name}</td>
                        <td className="px-4 py-2">{row.status ?? '—'}</td>
                        <td className="px-4 py-2 text-text-muted max-w-md truncate" title={row.notes ?? ''}>
                          {row.notes ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
            Book weight over time {thesisId === '_unlinked' ? '(unlinked)' : ''}
          </h2>
          {weightSeries.length === 0 ? (
            <p className="text-sm text-text-muted">No position history rows for this thesis.</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-border-subtle max-h-[280px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-bg-secondary z-10">
                  <tr className="border-b border-border-subtle text-left text-xs text-text-muted uppercase tracking-wider">
                    <th className="px-4 py-2">Date</th>
                    <th className="px-4 py-2 text-right">Weight %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {[...weightSeries].reverse().map((row) => (
                    <tr key={row.date}>
                      <td className="px-4 py-1.5 font-mono text-xs">{row.date}</td>
                      <td className="px-4 py-1.5 text-right font-mono tabular-nums">{row.weight_pct.toFixed(2)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {tickersOnLatest.size > 0 && (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
              Vehicles (latest snapshot {latestHistoryDate ?? '—'})
            </h2>
            <div className="flex flex-wrap gap-2">
              {[...tickersOnLatest].sort().map((t) => (
                <span
                  key={t}
                  className="px-2.5 py-1 rounded-md bg-white/[0.06] text-xs font-mono text-text-secondary"
                >
                  {t}
                </span>
              ))}
            </div>
          </section>
        )}

        {eventsForTickers.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Recent activity (linked tickers)</h2>
            <div className="overflow-x-auto rounded-xl border border-border-subtle">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-subtle text-left text-xs text-text-muted uppercase tracking-wider">
                    <th className="px-4 py-2">Date</th>
                    <th className="px-4 py-2">Ticker</th>
                    <th className="px-4 py-2">Event</th>
                    <th className="px-4 py-2 text-right">Weight %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {eventsForTickers.map((e, i) => (
                    <tr key={`${e.date}-${e.ticker}-${i}`}>
                      <td className="px-4 py-1.5 font-mono text-xs">{e.date}</td>
                      <td className="px-4 py-1.5 font-mono">{e.ticker}</td>
                      <td className="px-4 py-1.5">{e.event}</td>
                      <td className="px-4 py-1.5 text-right font-mono tabular-nums">
                        {e.weight_pct != null ? `${Number(e.weight_pct).toFixed(2)}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {relatedDocs.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Related PM documents</h2>
            <ul className="space-y-2">
              {relatedDocs.map((d) => (
                <li key={`${d.date}|${d.document_key}`}>
                  <Link
                    href={`/research?tab=daily&date=${encodeURIComponent(d.date)}&docKey=${encodeURIComponent(d.document_key)}`}
                    className="text-sm text-fin-blue hover:underline font-mono break-all"
                  >
                    {d.label} <span className="text-text-muted">({d.date})</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
