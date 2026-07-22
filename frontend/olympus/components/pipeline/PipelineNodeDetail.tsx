'use client';

import { useEffect, useState } from 'react';
import { Skeleton, SkeletonGroup } from '@digithings/web';
import { BookOpen, FileSearch, X } from 'lucide-react';
import { getLibraryDocumentById, type LibraryDocumentResult } from '@/lib/queries';
import type { LaidOutNode } from '@/lib/pipeline-layout';
import { PIPELINE_TOPOLOGY, pipelineNodeExplanation } from '@/lib/pipeline-topology';
import LibraryDocumentBody from '@/components/library/LibraryDocumentBody';

export interface PipelineNodeDetailProps {
  node?: LaidOutNode | null;
  documentKey: string | null;
  date: string;
  onClose: () => void;
}

export default function PipelineNodeDetail({
  node = null,
  documentKey,
  date,
  onClose,
}: PipelineNodeDetailProps) {
  const [doc, setDoc] = useState<LibraryDocumentResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const explanation = node ? pipelineNodeExplanation(node.stageId, node.id) : null;

  useEffect(() => {
    // No selection: the render derives the empty state from `documentKey`, so
    // there is nothing to set here (avoids setState-in-effect cascading renders).
    if (!documentKey) return;

    let cancelled = false;

    // All state writes happen inside the async callback, never synchronously in
    // the effect body (react-hooks/set-state-in-effect).
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchByDocumentKey(documentKey, date);
        if (!cancelled) {
          setDoc(result);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load document');
          setLoading(false);
        }
      }
    })();

    return () => { cancelled = true; };
  }, [documentKey, date]);

  // Responsive container: mobile = docked lower pane, desktop = right side panel.
  // Keeping mobile detail in flow leaves the stage navigator visible above it.
  return (
    <aside
      aria-label="Node detail"
      aria-live="polite"
      className={[
        'relative z-20 flex h-[46%] min-h-40 shrink-0 flex-col border-t border-hair bg-term-bg',
        'md:h-full md:w-[372px] md:min-h-0 md:border-l md:border-t-0',
      ].join(' ')}
    >
      {/* Header */}
      <div className="flex flex-shrink-0 items-start justify-between border-b border-hair px-4 py-3 md:px-5 md:py-4">
        <div className="min-w-0 flex-1">
          <div className="mb-1 text-xs font-bold uppercase text-accent">
            {documentKey ? 'Run artifact' : explanation ? 'Pipeline guide' : 'No selection'}
          </div>
          <div className="font-mono text-sm truncate text-ink">
            {node?.label ?? documentKey ?? '—'}
          </div>
          {explanation && (
            <div className="mt-1 font-mono text-xs text-ink-mute">
              Stage {explanation.stageNumber} of {PIPELINE_TOPOLOGY.length} · {explanation.stageLabel}
            </div>
          )}
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          className="ml-3 flex-shrink-0 w-7 h-7 flex items-center justify-center border border-hair rounded-lg text-ink-mute hover:text-ink transition-colors"
        >
          <X size={13} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-4 py-3 text-sm leading-relaxed text-ink-mute md:px-5 md:py-4">
        {/* Empty state */}
        {!documentKey && !explanation && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <FileSearch size={32} className="text-ink-mute opacity-40" />
            <p className="text-ink-mute text-sm">No document selected.</p>
            <p className="text-xs text-ink-mute/60">
              Select a node in the pipeline graph to view its output here.
            </p>
          </div>
        )}

        {!documentKey && explanation && (
          <div className="space-y-5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-hair bg-surface text-accent">
              <BookOpen size={17} aria-hidden />
            </div>
            <div>
              <p className="font-display text-lg leading-snug text-ink">{explanation.title}</p>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">
                {explanation.description}
              </p>
            </div>
            <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-hair bg-hair">
              <div className="bg-term-bg px-3 py-2.5">
                <dt className="font-mono text-xs uppercase text-ink-mute">
                  Stage
                </dt>
                <dd className="mt-1 text-xs text-ink">{explanation.stageLabel}</dd>
              </div>
              <div className="bg-term-bg px-3 py-2.5">
                <dt className="font-mono text-xs uppercase text-ink-mute">
                  Execution
                </dt>
                <dd className="mt-1 text-xs text-ink">{explanation.behavior}</dd>
              </div>
            </dl>
            <div className="border-t border-hair pt-4">
              <p className="font-mono text-xs uppercase text-ink-mute">
                This run
              </p>
              <p className="mt-2 text-xs leading-relaxed text-ink-mute">
                {node?.kind === 'stage'
                  ? 'The stage is a navigational overview. Expand it to inspect each operation and any artifacts published for the selected run.'
                  : node?.stateOnly
                    ? 'This operation updates pipeline state and does not publish a standalone document.'
                    : 'No standalone artifact is attached to this node for the selected run. Its role in the process remains the same.'}
              </p>
            </div>
          </div>
        )}

        {/* Loading — content-shaped sk shimmer stack (title line + body lines),
            not placeholder text (#1548; one loading grammar app-wide). */}
        {documentKey && loading && (
          <SkeletonGroup aria-label="Loading document" className="py-4 flex flex-col gap-3">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="w-full" />
            <Skeleton className="w-11/12" />
            <Skeleton className="w-4/5" />
          </SkeletonGroup>
        )}

        {/* Error */}
        {documentKey && !loading && error && (
          <div className="space-y-2">
            <p className="text-warn text-sm">{error}</p>
            <p className="text-xs text-ink-mute">
              This document may not be available for the selected date.
            </p>
          </div>
        )}

        {/* Document content — reused LibraryDocumentBody dispatch */}
        {documentKey && !loading && !error && doc && (
          <div className="space-y-4">
            {explanation && (
              <p className="border-b border-hair pb-3 text-xs leading-relaxed text-ink-mute">
                {explanation.description}
              </p>
            )}
            <LibraryDocumentBody
              view={doc.view}
              markdown={doc.markdown}
              payload={doc.payload}
              documentKey={doc.document_key}
              docDate={doc.date}
            />
          </div>
        )}

        {/* Not found */}
        {documentKey && !loading && !error && !doc && (
          <div className="space-y-2 py-4">
            <p className="text-ink-mute text-sm">
              No output found for <span className="font-mono text-ink">{documentKey}</span> on {date}.
            </p>
            <p className="text-xs text-ink-mute/70">
              This stage may not have run yet, or the output was not persisted.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}

/** Fetch a document by document_key + date via Supabase. Falls back gracefully. */
async function fetchByDocumentKey(
  documentKey: string,
  date: string,
): Promise<LibraryDocumentResult | null> {
  const { createClient } = await import('@supabase/supabase-js');
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;

  const supabase = createClient(url, key);
  // Defensive limit(1) rather than .maybeSingle(): maybeSingle ERRORS on >1
  // row, which rendered as "No output found" — the same failure class as the
  // #1538 digest headline (a retried/backfilled publish can duplicate a
  // (document_key, date) pair even though none exist today).
  const { data, error } = await supabase
    .from('documents')
    .select('id')
    .eq('document_key', documentKey)
    .eq('date', date)
    // Deterministic tiebreaker only — documents has no created_at column.
    .order('id', { ascending: false })
    .limit(1);

  const id = data?.[0]?.id;
  if (error || !id) return null;
  return await getLibraryDocumentById(id as string);
}
