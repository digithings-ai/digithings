'use client';

import { useCallback } from 'react';
import { Calendar, FileText } from 'lucide-react';
import MiniCalendar, { type MiniCalendarRunKind } from '@/components/library/MiniCalendar';
import DocumentExpandInline from '@/components/library/DocumentExpandInline';
import type { Doc } from '@/lib/types';
import type { LibraryDocumentResult } from '@/lib/queries';
import { groupPmDocs, canonicalPmTitle } from '@/components/portfolio/tabs/palette-and-format';

export default function AnalysisTab(props: {
  historyTimelineDates: string[];
  portfolioHistoryRunKindByDate: Map<string, MiniCalendarRunKind>;
  effHistoryDate: string | null;
  onSelectHistoryDate: (iso: string) => void;
  historyLatestDate: string | null;
  onClearHistoryDate: () => void;
  portfolioDocDates: Set<string>;
  positionHistoryDates: Set<string>;
  pmDocsForHistory: Doc[];
  pmActiveFile: Doc | null;
  pmLibraryDoc: LibraryDocumentResult | null;
  pmLoading: boolean;
  onOpenPmDocument: (doc: Doc) => void;
  onClosePmDocument: () => void;
}) {
  const {
    historyTimelineDates,
    portfolioHistoryRunKindByDate,
    effHistoryDate,
    onSelectHistoryDate,
    historyLatestDate,
    onClearHistoryDate,
    portfolioDocDates,
    positionHistoryDates,
    pmDocsForHistory,
    pmActiveFile,
    pmLibraryDoc,
    pmLoading,
    onOpenPmDocument,
    onClosePmDocument,
  } = props;

  const selectHistoryDate = useCallback(
    (iso: string) => {
      onSelectHistoryDate(iso);
    },
    [onSelectHistoryDate]
  );

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
            onClick={onClearHistoryDate}
            className="w-full text-xs py-2 rounded-lg border border-border-subtle text-text-secondary hover:text-white hover:bg-white/[0.04] transition-colors"
          >
            Jump to latest ({historyLatestDate})
          </button>
        ) : null}
      </div>

      <div className="flex-1 min-w-0 space-y-10">
        <section className="space-y-3">
          <div className="flex items-center gap-2 px-0.5">
            <Calendar size={15} className="text-fin-amber shrink-0" aria-hidden />
            <span className="text-xs font-medium text-text-muted font-mono">{effHistoryDate ?? '—'}</span>
            {effHistoryDate &&
            pmDocsForHistory.length === 0 &&
            !portfolioDocDates.has(effHistoryDate) &&
            positionHistoryDates.has(effHistoryDate) ? (
              <span className="text-xs text-text-muted ml-2">
                No PM files for this date; position history exists for this snapshot.
              </span>
            ) : null}
          </div>

          {pmDocsForHistory.length === 0 ? (
            <div className="glass-card px-5 py-10 text-center text-text-muted text-sm">
              No PM files for this date.
            </div>
          ) : (
            (() => {
              const groups = groupPmDocs(pmDocsForHistory);
              return groups.map((group) => {
                const groupKey =
                  group.kind === 'thesis' ? '__thesis__'
                  : group.kind === 'recommendations' ? '__recs__'
                  : group.kind === 'deliberations' ? '__dels__'
                  : '__memo__';
                const groupLabel =
                  group.kind === 'thesis' ? 'Thesis'
                  : group.kind === 'recommendations' ? 'Recommendations'
                  : group.kind === 'deliberations' ? 'Deliberations'
                  : 'PM Memo';
                return (
                  <div key={groupKey} className="glass-card p-0 overflow-hidden">
                    <div className="px-5 py-3 border-b border-border-subtle bg-bg-secondary">
                      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                        {groupLabel}
                      </h3>
                    </div>
                    <div className="divide-y divide-border-subtle">
                      {group.docs.map((d) => {
                        const active = pmActiveFile?.id === d.id;
                        return (
                          <div key={d.id}>
                            <button
                              type="button"
                              onClick={() => onOpenPmDocument(d)}
                              className={`w-full text-left px-5 py-3 flex items-center gap-3 hover:bg-white/[0.02] transition-colors ${
                                active ? 'bg-fin-amber/5' : ''
                              }`}
                            >
                              <FileText size={14} className="text-fin-amber/70 shrink-0" />
                              <span className="font-mono text-sm">{canonicalPmTitle(d.path)}</span>
                              <span className="ml-auto text-[11px] text-text-muted">{d.phase ?? ''}</span>
                            </button>
                            {active && pmActiveFile ? (
                              <DocumentExpandInline
                                accent="amber"
                                hideTitleBar
                                title={canonicalPmTitle(pmActiveFile.path)}
                                subtitle={pmActiveFile.date ?? null}
                                loading={pmLoading}
                                libraryDoc={pmLibraryDoc}
                              />
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              });
            })()
          )}
        </section>
      </div>
    </div>
  );
}
