'use client';

import { useEffect, useMemo, useState } from 'react';
import { ExternalLink, FileText, Users, X } from 'lucide-react';
import { Sheet, SheetClose, SheetContent, SheetTitle } from '@digithings/web';

import { SafeMarkdown } from '@/components/SafeMarkdown';
import { getBrief } from '@/lib/twelve-x/fetch';
import type { FxBriefRow } from '@/lib/twelve-x/types';

function asStringList(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((x) => String(x)).filter((s) => s.trim().length > 0);
  return [];
}

/**
 * The loaded-brief content (meta row, analysts, central thesis, markdown body,
 * source link). Split from the panel chrome — the chrome is the shared
 * @digithings/web Sheet, whose portal never renders under static SSR, so the
 * SSR content test targets this component directly (BriefPanel.test.tsx).
 */
export function BriefPanelBody({
  brief,
  loading,
  error,
}: {
  brief: FxBriefRow | null;
  loading: boolean;
  error: string | null;
}) {
  const analysts = useMemo(() => asStringList(brief?.analyst_names), [brief?.analyst_names]);

  if (loading) return <p className="text-sm text-ink-mute">Loading brief…</p>;
  if (error) return <p className="text-sm text-warn">{error}</p>;
  if (!brief) return null;

  return (
    <>
      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-mute">
        {brief.broker_name ? (
          <span className="flex items-center gap-1.5">
            <Users size={13} aria-hidden />
            <span className="font-medium text-ink-soft">{brief.broker_name}</span>
          </span>
        ) : null}
        {brief.report_date ? <span className="font-mono">report {brief.report_date}</span> : null}
        <span className="font-mono">run {brief.run_date}</span>
      </div>

      {analysts.length > 0 ? (
        <p className="text-xs text-ink-mute">By {analysts.join(', ')}</p>
      ) : null}

      {/* Central thesis */}
      {brief.central_thesis ? (
        <div className="rounded-lg border border-hair bg-ink/[0.02] p-3">
          <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
            Central thesis
          </h3>
          <SafeMarkdown className="prose prose-invert prose-sm max-w-none text-sm leading-snug text-ink">
            {brief.central_thesis}
          </SafeMarkdown>
        </div>
      ) : null}

      {/* Markdown body */}
      {brief.brief_markdown ? (
        <SafeMarkdown className="prose prose-invert max-w-none text-sm text-ink-soft">
          {brief.brief_markdown}
        </SafeMarkdown>
      ) : (
        <p className="text-sm text-ink-mute">No brief body available.</p>
      )}

      {/* Source link */}
      {brief.source_url ? (
        <a
          href={brief.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline"
        >
          <ExternalLink size={14} aria-hidden />
          Open source document
        </a>
      ) : null}
    </>
  );
}

/**
 * Slide-over panel for a single broker brief. Prop-driven (NOT URL-driven): the
 * parent owns the open/close state locally and passes the brief key down, so
 * opening a brief never touches the Next router — which is unreliable under this
 * suite's static export (see TwelveXClient). Lazily fetches by (source_file,
 * run_date) and renders broker, dates, central thesis, the markdown body, and a
 * source link.
 *
 * Chrome is the shared @digithings/web Sheet (#1450): Base UI's Dialog supplies
 * the modal focus trap, Escape/scrim dismiss, body-scroll lock, and aria wiring
 * that used to be hand-rolled here. Data fetching and content stay local
 * (BriefPanelBody). Closing unmounts instantly (today's behavior — no exit
 * animation); the Sheet's entrance slide honors prefers-reduced-motion via
 * controls-overlay.css.
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

  if (!open || !sourceFile) return null;

  return (
    <Sheet open onOpenChange={(next) => (next ? undefined : onClose())}>
      {/* The `!` overrides fight the sheet's deliberately unlayered per-side
          geometry (75% / 24rem cap) and same-layer base dress — this panel
          keeps its shipped full-bleed-mobile / max-w-xl / term-bg look
          (MIGRATION.md cascade-layering contract). The scrim re-dress is
          app-wide in globals.css. */}
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-full! max-w-xl! gap-0! bg-term-bg! shadow-2xl!"
      >
        {/* Grab bar — phone-only affordance hinting the sheet is dismissable. */}
        <div className="flex shrink-0 justify-center pt-2 sm:hidden" aria-hidden>
          <span className="h-1 w-9 rounded-full bg-ink/20" />
        </div>
        <div className="flex items-start gap-3 border-b border-hair px-5 py-4">
          <FileText size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
          <div className="min-w-0 flex-1">
            <SheetTitle className="truncate text-base font-semibold text-ink">
              {brief?.document_title || brief?.broker_name || 'Research brief'}
            </SheetTitle>
            <p className="truncate font-mono text-[11px] text-ink-mute">{sourceFile}</p>
          </div>
          <SheetClose
            aria-label="Close"
            className="-mr-1.5 -mt-1.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-ink-mute transition-colors hover:bg-ink/[0.06] hover:text-ink sm:h-9 sm:w-9"
          >
            <X size={18} aria-hidden />
          </SheetClose>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <BriefPanelBody brief={brief} loading={loading} error={error} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
