'use client';

import { useEffect, useState } from 'react';
import { Skeleton, SkeletonGroup } from '@digithings/web';
import { X, FileSearch } from 'lucide-react';
import { getLibraryDocumentById, type LibraryDocumentResult } from '@/lib/queries';
import LibraryDocumentBody from '@/components/library/LibraryDocumentBody';

export interface PipelineNodeDetailProps {
  documentKey: string | null;
  date: string;
  onClose: () => void;
}

export default function PipelineNodeDetail({ documentKey, date, onClose }: PipelineNodeDetailProps) {
  const [doc, setDoc] = useState<LibraryDocumentResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  // Responsive container: desktop = fixed side panel, mobile = bottom sheet
  return (
    <aside
      aria-label="Node detail"
      aria-live="polite"
      className={[
        // Mobile: bottom sheet
        'fixed inset-x-0 bottom-0 z-30 bg-term-bg border-t border-hair rounded-t-2xl',
        'h-[60vh] flex flex-col',
        // Desktop: right side panel (overrides the bottom sheet positioning)
        'md:inset-auto md:relative md:h-full md:w-[372px] md:border-t-0 md:border-l md:rounded-none',
      ].join(' ')}
    >
      {/* Header */}
      <div className="flex items-start justify-between px-5 py-4 border-b border-hair flex-shrink-0">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-bold tracking-[0.14em] uppercase text-accent mb-1">
            {documentKey ? 'Document' : 'No selection'}
          </div>
          <div className="font-mono text-sm truncate text-ink">
            {documentKey ?? '—'}
          </div>
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
      <div className="flex-1 overflow-y-auto px-5 py-4 text-sm text-ink-mute leading-relaxed">
        {/* Empty state */}
        {!documentKey && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <FileSearch size={32} className="text-ink-mute opacity-40" />
            <p className="text-ink-mute text-sm">No document selected.</p>
            <p className="text-[12px] text-ink-mute/60">
              Select a node in the pipeline graph to view its output here.
            </p>
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
            <p className="text-[12px] text-ink-mute">
              This document may not be available for the selected date.
            </p>
          </div>
        )}

        {/* Document content — reused LibraryDocumentBody dispatch */}
        {documentKey && !loading && !error && doc && (
          <LibraryDocumentBody
            view={doc.view}
            markdown={doc.markdown}
            payload={doc.payload}
            documentKey={doc.document_key}
            docDate={doc.date}
          />
        )}

        {/* Not found */}
        {documentKey && !loading && !error && !doc && (
          <div className="space-y-2 py-4">
            <p className="text-ink-mute text-sm">
              No output found for <span className="font-mono text-ink">{documentKey}</span> on {date}.
            </p>
            <p className="text-[12px] text-ink-mute/70">
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
  const { data, error } = await supabase
    .from('documents')
    .select('id')
    .eq('document_key', documentKey)
    .eq('date', date)
    .maybeSingle();

  if (error || !data?.id) return null;
  return await getLibraryDocumentById(data.id as string);
}
