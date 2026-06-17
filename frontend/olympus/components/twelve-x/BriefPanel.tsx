'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ExternalLink, FileText, Users, X } from 'lucide-react';

import { SafeMarkdown } from '@/components/SafeMarkdown';
import { getBrief } from '@/lib/twelve-x/fetch';
import type { FxBriefRow } from '@/lib/twelve-x/types';

/**
 * Build an href that sets `?brief=<source_file>` on the current path while
 * preserving every other query param (e.g. ?tab=). Use this to wire a
 * "drill to brief" affordance into any tab.
 */
export function briefHref(
  pathname: string,
  searchParams: URLSearchParams,
  sourceFile: string
): string {
  const p = new URLSearchParams(searchParams.toString());
  p.set('brief', sourceFile);
  const s = p.toString();
  return s ? `${pathname}?${s}` : pathname;
}

function asStringList(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((x) => String(x)).filter((s) => s.trim().length > 0);
  return [];
}

/**
 * Slide-over panel that opens whenever `?brief=<source_file>` is present in the
 * URL. Lazily fetches the brief (run_date, source_file) and renders broker,
 * dates, central thesis, the SafeMarkdown body, and a source link. Closing
 * clears the `brief` param while preserving the rest of the query.
 */
export default function BriefPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const sourceFile = searchParams.get('brief');
  const runDate = searchParams.get('briefDate');

  const [brief, setBrief] = useState<FxBriefRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = useCallback(() => {
    const p = new URLSearchParams(searchParams.toString());
    p.delete('brief');
    p.delete('briefDate');
    const s = p.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  }, [pathname, router, searchParams]);

  // Reset the resolved brief whenever the key clears. Adjusting state during
  // render (rather than synchronously inside an effect) avoids the cascading-
  // render lint — see https://react.dev/learn/you-might-not-need-an-effect.
  if (!sourceFile && (brief !== null || error !== null)) {
    setBrief(null);
    setError(null);
  }

  // Lazily resolve the brief whenever the key changes. All state writes live
  // inside the async closure (off the synchronous effect body) so we don't
  // trigger a cascading render on mount — see the React effects guidance:
  // https://react.dev/learn/you-might-not-need-an-effect.
  useEffect(() => {
    if (!sourceFile) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const b = await getBrief(sourceFile, runDate);
        if (cancelled) return;
        setBrief(b);
        if (!b) setError('Brief not found.');
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load brief');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sourceFile, runDate]);

  // Close on Escape while open.
  useEffect(() => {
    if (!sourceFile) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [sourceFile, close]);

  const analysts = useMemo(() => asStringList(brief?.analyst_names), [brief?.analyst_names]);

  if (!sourceFile) return null;

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Research brief">
      {/* Scrim */}
      <button
        type="button"
        aria-label="Close brief"
        onClick={close}
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
      />

      {/* Panel */}
      <div className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l border-border-subtle bg-bg-secondary shadow-2xl">
        <div className="flex items-start gap-3 border-b border-border-subtle px-5 py-4">
          <FileText size={18} className="mt-0.5 shrink-0 text-fin-blue" aria-hidden />
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-base font-semibold text-text-primary">
              {brief?.document_title || brief?.broker_name || 'Research brief'}
            </h2>
            <p className="truncate font-mono text-[11px] text-text-muted">{sourceFile}</p>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close"
            className="shrink-0 rounded-lg p-1.5 text-text-muted transition-colors hover:bg-white/[0.06] hover:text-text-primary"
          >
            <X size={18} aria-hidden />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {loading ? (
            <p className="text-sm text-text-muted">Loading brief…</p>
          ) : error ? (
            <p className="text-sm text-fin-red">{error}</p>
          ) : brief ? (
            <>
              {/* Meta row */}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-text-muted">
                {brief.broker_name ? (
                  <span className="flex items-center gap-1.5">
                    <Users size={13} aria-hidden />
                    <span className="font-medium text-text-secondary">{brief.broker_name}</span>
                  </span>
                ) : null}
                {brief.report_date ? (
                  <span className="font-mono">report {brief.report_date}</span>
                ) : null}
                <span className="font-mono">run {brief.run_date}</span>
              </div>

              {analysts.length > 0 ? (
                <p className="text-xs text-text-muted">By {analysts.join(', ')}</p>
              ) : null}

              {/* Central thesis */}
              {brief.central_thesis ? (
                <div className="rounded-lg border border-border-subtle bg-white/[0.02] p-3">
                  <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                    Central thesis
                  </h3>
                  <p className="text-sm leading-snug text-text-primary">{brief.central_thesis}</p>
                </div>
              ) : null}

              {/* Markdown body */}
              {brief.brief_markdown ? (
                <SafeMarkdown className="prose prose-invert max-w-none text-sm text-text-secondary">
                  {brief.brief_markdown}
                </SafeMarkdown>
              ) : (
                <p className="text-sm text-text-muted">No brief body available.</p>
              )}

              {/* Source link */}
              {brief.source_url ? (
                <a
                  href={brief.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-fin-blue hover:underline"
                >
                  <ExternalLink size={14} aria-hidden />
                  Open source document
                </a>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
