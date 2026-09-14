'use client';

import { useDeferredValue, useMemo, useState } from 'react';
import { FileText, Search, X } from 'lucide-react';
import type { PipelineArtifact } from '@/lib/pipeline-graph-data';

function artifactFamily(artifact: PipelineArtifact): string {
  const prefix = artifact.documentKey.split('/')[0];
  if (artifact.documentKey.startsWith('document-deltas/')) return 'Document deltas';
  if (prefix === 'analyst') return 'Analyst reports';
  if (prefix === 'deliberation') return 'Deliberations';
  if (prefix === 'commit-run') return 'Commit records';
  return 'Run outputs';
}

function artifactLabel(artifact: PipelineArtifact): string {
  return artifact.title?.trim() || artifact.documentKey;
}

export default function PipelineArtifactLedger({
  artifacts,
  date,
  selectedDocumentKey,
  onSelect,
  onClose,
}: {
  artifacts: PipelineArtifact[];
  date: string;
  selectedDocumentKey: string | null;
  onSelect: (documentKey: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());
  const groups = useMemo(() => {
    const filtered = deferredQuery
      ? artifacts.filter((artifact) => [
          artifact.documentKey,
          artifact.title,
          artifact.docType,
          artifact.category,
          artifact.segment,
          artifact.sector,
        ].some((value) => value?.toLowerCase().includes(deferredQuery)))
      : artifacts;

    return Object.entries(
      Object.groupBy(filtered, artifactFamily),
    ).map(([label, items]) => ({ label, items: items ?? [] }));
  }, [artifacts, deferredQuery]);

  return (
    <aside
      aria-label="All pipeline artifacts"
      className="fixed inset-0 z-[1050] flex h-dvh w-full flex-col overflow-hidden bg-term-bg pt-[env(safe-area-inset-top)] md:relative md:inset-auto md:z-20 md:h-full md:w-[min(42vw,520px)] md:min-h-0 md:border-l md:border-hair md:pt-0"
    >
      <header className="flex items-start justify-between gap-3 border-b border-hair px-4 py-3 md:px-5 md:py-4">
        <div className="min-w-0">
          <h2 className="font-display text-xl text-ink">All artifacts</h2>
          <p className="mt-0.5 font-mono text-xs text-ink-mute">
            {artifacts.length} persisted outputs · {date}
          </p>
        </div>
        <button
          type="button"
          aria-label="Close artifact ledger"
          onClick={onClose}
          className="flex h-11 w-11 shrink-0 items-center justify-center border border-hair text-ink-mute transition-colors hover:text-ink md:h-8 md:w-8"
        >
          <X size={18} aria-hidden />
        </button>
      </header>

      <div className="border-b border-hair p-3 md:px-5">
        <label className="relative block">
          <span className="sr-only">Search artifacts</span>
          <Search
            size={15}
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-mute"
          />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search keys, types, or tickers"
            className="h-10 w-full border border-hair bg-surface pl-9 pr-3 font-mono text-xs text-ink outline-none transition-colors placeholder:text-ink-mute/70 focus:border-accent"
          />
        </label>
      </div>

      <div className="flex-1 overflow-y-auto overscroll-contain px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] md:px-5">
        {groups.length > 0 ? groups.map((group) => (
          <section key={group.label} className="mb-5 last:mb-0">
            <div className="mb-2 flex items-center justify-between gap-3">
              <h3 className="font-mono text-[0.65rem] font-semibold uppercase text-ink-mute">
                {group.label}
              </h3>
              <span className="font-mono text-xs tabular-nums text-ink-mute">
                {group.items.length}
              </span>
            </div>
            <div className="divide-y divide-hair border-y border-hair">
              {group.items.map((artifact) => {
                const selected = artifact.documentKey === selectedDocumentKey;
                return (
                  <button
                    key={artifact.documentKey}
                    type="button"
                    aria-current={selected ? 'page' : undefined}
                    onClick={() => onSelect(artifact.documentKey)}
                    className={`flex min-h-14 w-full items-start gap-3 px-2 py-2.5 text-left transition-colors hover:bg-accent/[0.04] ${
                      selected ? 'bg-accent/[0.08]' : ''
                    }`}
                  >
                    <FileText size={16} aria-hidden className="mt-0.5 shrink-0 text-accent" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-ink">
                        {artifactLabel(artifact)}
                      </span>
                      <span className="mt-0.5 block break-all font-mono text-[0.65rem] leading-relaxed text-ink-mute">
                        {artifact.documentKey}
                      </span>
                    </span>
                    {artifact.docType ? (
                      <span className="max-w-28 shrink-0 text-right font-mono text-[0.6rem] uppercase leading-tight text-ink-mute">
                        {artifact.docType}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </section>
        )) : (
          <p className="py-8 text-center text-sm text-ink-mute">No artifacts match this search.</p>
        )}
      </div>
    </aside>
  );
}