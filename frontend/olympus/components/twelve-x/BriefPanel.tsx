'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ExternalLink, FileText, Users, X } from 'lucide-react';

import { SafeMarkdown } from '@/components/SafeMarkdown';
import { getBrief } from '@/lib/twelve-x/fetch';
import type { FxBriefRow } from '@/lib/twelve-x/types';

function asStringList(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((x) => String(x)).filter((s) => s.trim().length > 0);
  return [];
}

/**
 * Slide-over panel for a single broker brief. Prop-driven (NOT URL-driven): the
 * parent owns the open/close state locally and passes the brief key down, so
 * opening a brief never touches the Next router — which is unreliable under this
 * suite's static export (see TwelveXClient). Lazily fetches by (source_file,
 * run_date) and renders broker, dates, central thesis, the markdown body, and a
 * source link.
 *
 * `runDate` pins the right brief when two runs share a `source_file`; `getBrief`
 * falls back to the latest run carrying that file when it's null.
 */
export default function BriefPanel({
  open,
  sourceFile,
  runDate,
  onClose,
}: {
  open: boolean;
  sourceFile: string | null;
  runDate: string | null;
  onClose: () => void;
}) {
  const [brief, setBrief] = useState<FxBriefRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset the resolved brief whenever the panel closes / key clears. Adjusting
  // state during render (rather than in an effect) avoids the cascading-render
  // lint — see https://react.dev/learn/you-might-not-need-an-effect.
  if (!open && (brief !== null || error !== null)) {
    setBrief(null);
    setError(null);
  }

  // Lazily resolve the brief whenever the key changes. All state writes live in
  // the async closure so we don't trigger a cascading render on mount.
  useEffect(() => {
    if (!open || !sourceFile) return;
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
  }, [open, sourceFile, runDate]);

  // Close on Escape while open.
  const handleClose = useCallback(() => onClose(), [onClose]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, handleClose]);

  // Lock body scroll while the panel is open (mirrors the app nav drawer), so
  // the page behind the full-bleed mobile sheet doesn't scroll under it.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const analysts = useMemo(() => asStringList(brief?.analyst_names), [brief?.analyst_names]);

  if (!open || !sourceFile) return null;

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Research brief">
      {/* Scrim */}
      <button
        type="button"
        aria-label="Close brief"
        onClick={handleClose}
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
      />

      {/* Panel */}
      <div className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l border-border-subtle bg-bg-secondary shadow-2xl">
        {/* Grab bar — phone-only affordance hinting the sheet is dismissable. */}
        <div className="flex shrink-0 justify-center pt-2 sm:hidden" aria-hidden>
          <span className="h-1 w-9 rounded-full bg-white/20" />
        </div>
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
            onClick={handleClose}
            aria-label="Close"
            className="-mr-1.5 -mt-1.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/[0.06] hover:text-text-primary sm:h-9 sm:w-9"
          >
            <X size={18} aria-hidden />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
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
                  <SafeMarkdown className="prose prose-invert prose-sm max-w-none text-sm leading-snug text-text-primary">
                    {brief.central_thesis}
                  </SafeMarkdown>
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
