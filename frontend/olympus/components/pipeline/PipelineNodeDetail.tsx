'use client';

import { useEffect, useState } from 'react';
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
    if (!documentKey) {
      setDoc(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    // Fetch by document_key + date filter
    void (async () => {
      try {
        // getLibraryDocumentById takes an id; we use document_key as a lookup hint.
        // The real lookup uses the supabase query via document_key match.
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
        'fixed inset-x-0 bottom-0 z-30 bg-[var(--panel)] border-t border-border rounded-t-2xl',
        'h-[60vh] flex flex-col',
        // Desktop: right side panel (overrides the bottom sheet positioning)
        'md:inset-auto md:relative md:h-full md:w-[372px] md:border-t-0 md:border-l md:rounded-none',
      ].join(' ')}
    >
      {/* Header */}
      <div className="flex items-start justify-between px-5 py-4 border-b border-border flex-shrink-0">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-bold tracking-[0.14em] uppercase text-fin-blue mb-1">
            {documentKey ? 'Document' : 'No selection'}
          </div>
          <div className="font-mono text-sm truncate text-foreground">
            {documentKey ?? '—'}
          </div>
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          className="ml-3 flex-shrink-0 w-7 h-7 flex items-center justify-center border border-border rounded-lg text-muted hover:text-foreground transition-colors"
        >
          <X size={13} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-5 py-4 text-sm text-muted leading-relaxed">
        {/* Empty state */}
        {!documentKey && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <FileSearch size={32} className="text-muted opacity-40" />
            <p className="text-muted text-sm">No document selected.</p>
            <p className="text-[12px] text-muted/60">
              Select a node in the pipeline graph to view its output here.
            </p>
          </div>
        )}

        {/* Loading */}
        {documentKey && loading && (
          <div className="text-muted text-sm py-4">Loading document…</div>
        )}

        {/* Error */}
        {documentKey && !loading && error && (
          <div className="space-y-2">
            <p className="text-fin-amber text-sm">{error}</p>
            <p className="text-[12px] text-muted">
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
            <p className="text-muted text-sm">
              No output found for <span className="font-mono text-foreground">{documentKey}</span> on {date}.
            </p>
            <p className="text-[12px] text-muted/70">
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
