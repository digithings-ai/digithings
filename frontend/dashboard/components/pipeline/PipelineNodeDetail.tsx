'use client';

import { useEffect, useState } from 'react';
import { Skeleton, SkeletonGroup } from '@digithings/web';
import { getLibraryDocumentById, type LibraryDocumentResult } from '@/lib/queries';
import { pipelineNodeRunStatusLabel } from '@/lib/pipeline-layout';
import type { LaidOutNode } from '@/lib/pipeline-layout';
import { PIPELINE_TOPOLOGY, pipelineNodeExplanation } from '@/lib/pipeline-topology';
import LibraryDocumentBody from '@/components/library/LibraryDocumentBody';
import DetailPanelHeaderActions, {
  type DetailPanelSize,
} from '@/components/DetailPanelHeaderActions';

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
  // Reader ergonomics (#1679): comfortable (default) / wide / full-screen. Desktop
  // only — the mobile docked pane keeps its height-based layout untouched.
  const [size, setSize] = useState<DetailPanelSize>('default');
  const explanation = node && node.kind !== 'stage'
    ? pipelineNodeExplanation(node.stageId, node.id)
    : null;
  const runStatus = node?.runStatus
    ?? (documentKey ? 'persisted-artifact' : null);

  useEffect(() => {
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

  if (!documentKey) return null;

  // Mobile detail replaces the browser as a full-page surface; closing it returns to
  // the exact Pipeline selection. Desktop keeps the in-workspace side panel.
  return (
    <aside
      aria-label="Node detail"
      aria-live="polite"
      className={[
        'fixed inset-0 z-[1100] flex h-dvh w-full shrink-0 flex-col overflow-hidden bg-term-bg',
        'pt-[env(safe-area-inset-top)] md:pt-0',
        // Desktop reader sizes (#1679): comfortable / wide / full-screen; mobile is
        // always the full-page surface from the develop-side mobile pass.
        size === 'full'
          ? 'md:fixed md:inset-0 md:z-50 md:h-full md:w-full'
          : size === 'wide'
            ? 'md:relative md:inset-auto md:z-20 md:h-full md:w-[min(80vw,960px)] md:min-h-0 md:border-l md:border-hair'
            : 'md:relative md:inset-auto md:z-20 md:h-full md:w-[min(58vw,680px)] md:min-h-0 md:border-l md:border-hair',
      ].join(' ')}
    >
      {/* Header */}
      <div className="flex flex-shrink-0 items-start justify-between border-b border-hair px-4 py-3 md:px-5 md:py-4">
        <div className="min-w-0 flex-1">
          <div className="mb-1 text-xs font-bold uppercase text-accent">
            {runStatus
              ? pipelineNodeRunStatusLabel(runStatus)
              : 'Document'}
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
        <DetailPanelHeaderActions size={size} onSizeChange={setSize} onClose={onClose} />
      </div>

      {/* Body */}
      <div
        className={[
          'flex-1 overflow-y-auto overscroll-contain px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] text-sm leading-relaxed text-ink-mute md:px-5 md:py-4',
          size === 'full' ? 'md:mx-auto md:w-full md:max-w-3xl' : '',
        ].join(' ')}
      >
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

  // Secondary client — do not share GoTrue storage with the auth singleton.
  const supabase = createClient(url, key, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  });
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
