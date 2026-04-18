'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { Change } from 'diff';
import { diffLines, diffWords } from 'diff';
import { ChevronDown } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  fetchDocumentDiffAnchors,
  loadDocumentDiff,
  type DocumentDiffCompareKind,
  type DocumentDiffPair,
} from '@/lib/queries';

type ViewScope = 'current' | 'difference';
type DiffLayout = 'inline' | 'split';

function isTableLine(s: string): boolean {
  return s.trimStart().startsWith('|');
}

function lineDiffToItems(parts: Change[]): LineDiffItem[] {
  const items: LineDiffItem[] = [];
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (p.added) {
      items.push({ kind: 'added', text: p.value });
      continue;
    }
    if (p.removed) {
      const next = parts[i + 1];
      if (next?.added) {
        items.push({ kind: 'wordSwap', oldText: p.value, newText: next.value });
        i += 1;
      } else {
        items.push({ kind: 'removed', text: p.value });
      }
      continue;
    }
    items.push({ kind: 'equal', text: p.value });
  }
  return items;
}

type LineDiffItem =
  | { kind: 'equal'; text: string }
  | { kind: 'removed'; text: string }
  | { kind: 'added'; text: string }
  | { kind: 'wordSwap'; oldText: string; newText: string };

function WordSwapBlock({ oldText, newText }: { oldText: string; newText: string }) {
  const wparts = diffWords(oldText, newText);
  const mono = isTableLine(oldText) || isTableLine(newText);
  return (
    <div
      className={`whitespace-pre-wrap px-3 py-1 border-l-2 border-amber-500/50 bg-bg-secondary/60 leading-relaxed text-text-secondary/95 ${
        mono ? 'font-mono text-[12px]' : 'text-sm font-sans'
      }`}
    >
      {wparts.map((w, j) => {
        if (w.added) {
          return (
            <span
              key={j}
              className="bg-emerald-950/55 text-emerald-100 rounded-sm px-0.5 border-b border-emerald-500/60"
            >
              {w.value}
            </span>
          );
        }
        if (w.removed) {
          return (
            <span
              key={j}
              className="bg-red-950/50 text-red-100/95 line-through decoration-red-300/50 rounded-sm px-0.5"
            >
              {w.value}
            </span>
          );
        }
        return <span key={j}>{w.value}</span>;
      })}
    </div>
  );
}

function comparePresetLabel(kind: 'previous_day' | 'delta_baseline', anchors: { prev: string | null; base: string | null }): string {
  if (kind === 'delta_baseline') {
    return anchors.base ? `Delta baseline (${anchors.base})` : 'Delta baseline';
  }
  return anchors.prev ? `Previous run (${anchors.prev})` : 'Previous run';
}

function compareModeFootnote(pair: DocumentDiffPair): string {
  switch (pair.compareMode) {
    case 'baseline_doc':
      return `Delta vs baseline file "${pair.compareKey}" from ${pair.compareDate}`;
    case 'delta_baseline':
      return `Same artifact at delta baseline ${pair.compareDate}`;
    case 'custom_date':
      return `Same artifact at ${pair.compareDate}`;
    case 'previous_day':
    default:
      return `Prior run ${pair.compareDate}`;
  }
}

function segmentOuterClass() {
  return 'inline-flex rounded-lg border border-border-subtle p-0.5 bg-bg-secondary/80 gap-0.5';
}

function segmentBtnClass(active: boolean) {
  return `rounded-md px-3 py-1.5 text-xs font-medium border transition-colors ${
    active
      ? 'border-fin-blue/40 bg-fin-blue/15 text-fin-blue'
      : 'border-transparent text-text-muted hover:text-text-primary hover:bg-white/[0.06]'
  }`;
}

function DocumentArtifactCompareDropdown({
  anchors,
  compareKind,
  customCompareDate,
  canPrev,
  canBase,
  onSelectPreset,
}: {
  anchors: { prev: string | null; base: string | null };
  compareKind: DocumentDiffCompareKind;
  customCompareDate: string;
  canPrev: boolean;
  canBase: boolean;
  onSelectPreset: (k: 'previous_day' | 'delta_baseline') => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const summaryLabel =
    compareKind === 'custom_date' && /^\d{4}-\d{2}-\d{2}$/.test(customCompareDate.trim())
      ? `Custom (${customCompareDate.trim()})`
      : compareKind === 'delta_baseline'
        ? comparePresetLabel('delta_baseline', anchors)
        : comparePresetLabel('previous_day', anchors);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border border-border-subtle bg-bg-secondary text-text-secondary hover:border-fin-blue/40 hover:text-text-primary transition-colors"
        aria-expanded={open ? 'true' : 'false'}
        aria-haspopup="listbox"
      >
        <span className="max-w-[min(100vw-8rem,14rem)] truncate">{summaryLabel}</span>
        <ChevronDown size={14} className={`opacity-70 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-[60] mt-1 w-[min(100vw-2rem,20rem)] rounded-lg border border-border-subtle bg-[#141414] shadow-xl overflow-hidden">
          <div role="listbox" aria-label="Compare document to" className="py-1">
            <button
              type="button"
              role="option"
              aria-selected={compareKind === 'previous_day' ? 'true' : 'false'}
              disabled={!canPrev}
              onClick={() => {
                if (!canPrev) return;
                onSelectPreset('previous_day');
                setOpen(false);
              }}
              className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                !canPrev
                  ? 'text-text-muted opacity-40 cursor-not-allowed'
                  : compareKind === 'previous_day'
                    ? 'bg-fin-blue/15 text-fin-blue'
                    : 'text-text-secondary hover:bg-white/[0.06] hover:text-text-primary'
              }`}
            >
              {comparePresetLabel('previous_day', anchors)}
            </button>
            <button
              type="button"
              role="option"
              aria-selected={compareKind === 'delta_baseline' ? 'true' : 'false'}
              disabled={!canBase}
              onClick={() => {
                if (!canBase) return;
                onSelectPreset('delta_baseline');
                setOpen(false);
              }}
              className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                !canBase
                  ? 'text-text-muted opacity-40 cursor-not-allowed'
                  : compareKind === 'delta_baseline'
                    ? 'bg-fin-blue/15 text-fin-blue'
                    : 'text-text-secondary hover:bg-white/[0.06] hover:text-text-primary'
              }`}
            >
              {comparePresetLabel('delta_baseline', anchors)}
            </button>
          </div>
          <p className="text-[10px] text-text-muted px-2.5 py-1.5 border-t border-border-subtle bg-bg-secondary/80">
            Previous or baseline — or use the date field for a custom run day.
          </p>
        </div>
      )}
    </div>
  );
}

export default function GenericDiffDocumentView({
  docDate,
  documentKey,
  payload,
  fallbackMarkdown,
}: {
  docDate: string;
  documentKey: string;
  payload: Record<string, unknown> | null;
  fallbackMarkdown: string;
}) {
  const [viewScope, setViewScope] = useState<ViewScope>('current');
  const [diffLayout, setDiffLayout] = useState<DiffLayout>('inline');
  const [compareKind, setCompareKind] = useState<DocumentDiffCompareKind>('previous_day');
  const [customCompareDate, setCustomCompareDate] = useState('');
  const [anchorsLoading, setAnchorsLoading] = useState(true);
  const [pairLoading, setPairLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anchors, setAnchors] = useState<{ prev: string | null; base: string | null }>({
    prev: null,
    base: null,
  });
  const [pair, setPair] = useState<DocumentDiffPair | null>(null);
  const preferPreviousRef = useRef(false);

  useEffect(() => {
    if (!preferPreviousRef.current || viewScope !== 'difference' || anchorsLoading) return;
    preferPreviousRef.current = false;
    /* eslint-disable react-hooks/set-state-in-effect -- sync compare preset when opening Difference */
    setCustomCompareDate('');
    if (anchors.prev) setCompareKind('previous_day');
    else if (anchors.base) setCompareKind('delta_baseline');
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [anchors.prev, anchors.base, anchorsLoading, viewScope]);

  useEffect(() => {
    let cancelled = false;
    /* eslint-disable react-hooks/set-state-in-effect -- fetch lifecycle for compare anchors */
    setAnchorsLoading(true);
    setError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    fetchDocumentDiffAnchors(docDate, documentKey, payload)
      .then((a) => {
        if (!cancelled) setAnchors({ prev: a.previousDayDate, base: a.deltaBaselineDate });
      })
      .catch(() => {
        if (!cancelled) setAnchors({ prev: null, base: null });
      })
      .finally(() => {
        if (!cancelled) setAnchorsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [docDate, documentKey, payload]);

  useEffect(() => {
    if (viewScope === 'current') return;
    let cancelled = false;
    /* eslint-disable react-hooks/set-state-in-effect -- fetch lifecycle for diff pair */
    setPairLoading(true);
    setError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    loadDocumentDiff(docDate, documentKey, payload, {
      compare: compareKind,
      customCompareDate: compareKind === 'custom_date' ? customCompareDate : undefined,
    })
      .then((p) => {
        if (!cancelled) setPair(p);
      })
      .catch((e) => {
        if (!cancelled) {
          setPair(null);
          setError(e instanceof Error ? e.message : 'Failed to load diff');
        }
      })
      .finally(() => {
        if (!cancelled) setPairLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [docDate, documentKey, payload, compareKind, customCompareDate, viewScope]);

  const lineItems = useMemo(() => {
    if (!pair) return [];
    return lineDiffToItems(diffLines(pair.beforeMarkdown, pair.afterMarkdown));
  }, [pair]);

  const hasDiff = useMemo(() => lineItems.some((it) => it.kind !== 'equal'), [lineItems]);

  const canPrev = !!anchors.prev;
  const canBase = !!anchors.base;
  const customReady = compareKind !== 'custom_date' || /^\d{4}-\d{2}-\d{2}$/.test(customCompareDate.trim());

  if (anchorsLoading) {
    return <p className="text-text-muted text-sm">Loading document…</p>;
  }

  const toolbar = (
    <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
      <div className={segmentOuterClass()}>
        <button
          type="button"
          className={segmentBtnClass(viewScope === 'current')}
          onClick={() => {
            setViewScope('current');
            setPair(null);
            setError(null);
          }}
        >
          Current
        </button>
        <button
          type="button"
          className={segmentBtnClass(viewScope === 'difference')}
          onClick={() => {
            preferPreviousRef.current = true;
            setViewScope('difference');
          }}
        >
          Difference
        </button>
      </div>

      {viewScope === 'difference' ? (
        <>
          <div className={segmentOuterClass()}>
            <button type="button" className={segmentBtnClass(diffLayout === 'inline')} onClick={() => setDiffLayout('inline')}>
              Inline
            </button>
            <button type="button" className={segmentBtnClass(diffLayout === 'split')} onClick={() => setDiffLayout('split')}>
              Side by side
            </button>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
            <DocumentArtifactCompareDropdown
              anchors={anchors}
              compareKind={compareKind}
              customCompareDate={customCompareDate}
              canPrev={canPrev}
              canBase={canBase}
              onSelectPreset={(k) => {
                setCompareKind(k);
                setCustomCompareDate('');
              }}
            />
            <label className="flex flex-col gap-0.5 min-w-[10.5rem]">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">Or compare to date</span>
              <input
                type="date"
                value={customCompareDate}
                onChange={(e) => {
                  const v = e.target.value;
                  setCustomCompareDate(v);
                  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) setCompareKind('custom_date');
                  else if (canPrev) setCompareKind('previous_day');
                  else if (canBase) setCompareKind('delta_baseline');
                }}
                className="rounded-md border border-border-subtle bg-bg-secondary px-2 py-1.5 text-xs text-text-primary font-mono focus:outline-none focus:ring-1 focus:ring-inset focus:ring-fin-blue/30"
                aria-label="Compare this document to a custom run date"
              />
            </label>
          </div>
        </>
      ) : null}
    </div>
  );

  if (viewScope === 'current') {
    return (
      <div className="space-y-4">
        {toolbar}
        <div className="prose prose-invert max-w-none text-sm leading-relaxed">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
        </div>
      </div>
    );
  }

  if (!customReady) {
    return (
      <div className="space-y-4">
        {toolbar}
        <p className="text-text-muted text-sm">Pick a compare date, or clear the custom date field to use a preset.</p>
      </div>
    );
  }

  if (pairLoading) {
    return (
      <div className="space-y-4">
        {toolbar}
        <p className="text-text-muted text-sm">Loading comparison…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-3">
        {toolbar}
        <p className="text-fin-red text-xs">{error}</p>
        <div className="prose prose-invert max-w-none text-sm">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
        </div>
      </div>
    );
  }

  if (!pair) {
    return (
      <div className="space-y-4">
        {toolbar}
        <p className="text-text-muted text-sm">
          No comparison document for this choice — showing the current version below.
        </p>
        <div className="prose prose-invert max-w-none text-sm leading-relaxed">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {toolbar}
      <p className="text-text-muted text-[11px]" title={compareModeFootnote(pair)}>
        Diff vs <span className="font-mono text-fin-blue">{pair.compareDate}</span>
        <span className="text-text-muted"> · {compareModeFootnote(pair)}</span>
      </p>

      {diffLayout === 'inline' ? (
        <div>
          {!hasDiff ? (
            <p className="text-text-muted text-sm mb-3">No text changes vs comparison version.</p>
          ) : (
            <p className="text-[10px] uppercase tracking-wider text-text-muted mb-2">
              Line diff with word highlights where a line was replaced · removed (red) · added (green)
            </p>
          )}
          <div className="rounded-lg border border-border-subtle bg-bg-secondary/40 text-sm leading-relaxed max-h-[min(62vh,720px)] overflow-auto">
            {lineItems.map((item, i) => {
              if (item.kind === 'wordSwap') {
                return <WordSwapBlock key={i} oldText={item.oldText} newText={item.newText} />;
              }
              const mono = isTableLine(item.text);
              const fontClass = mono ? 'font-mono text-[12px]' : 'font-sans';
              if (item.kind === 'added') {
                return (
                  <span
                    key={i}
                    className={`block whitespace-pre-wrap px-3 py-0.5 bg-emerald-950/50 text-emerald-100 border-l-2 border-emerald-500/80 ${fontClass}`}
                  >
                    {item.text}
                  </span>
                );
              }
              if (item.kind === 'removed') {
                return (
                  <span
                    key={i}
                    className={`block whitespace-pre-wrap px-3 py-0.5 bg-red-950/45 text-red-100/95 border-l-2 border-red-500/70 line-through decoration-red-300/50 ${fontClass}`}
                  >
                    {item.text}
                  </span>
                );
              }
              return (
                <span
                  key={i}
                  className={`block whitespace-pre-wrap px-3 py-0.5 text-text-secondary/90 ${fontClass}`}
                >
                  {item.text}
                </span>
              );
            })}
          </div>
        </div>
      ) : (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-text-muted mb-2">
            Comparison (left) · current (right)
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[min(62vh,720px)] overflow-auto">
            <div className="rounded-lg border border-border-subtle bg-bg-secondary/30 p-3 min-h-0 overflow-auto">
              <p className="text-[10px] font-mono text-text-muted mb-2">Compare — {pair.compareDate}</p>
              <div className="prose prose-invert max-w-none text-sm leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{pair.beforeMarkdown}</ReactMarkdown>
              </div>
            </div>
            <div className="rounded-lg border border-border-subtle bg-bg-secondary/30 p-3 min-h-0 overflow-auto">
              <p className="text-[10px] font-mono text-text-muted mb-2">Current — {pair.targetDate}</p>
              <div className="prose prose-invert max-w-none text-sm leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{pair.afterMarkdown}</ReactMarkdown>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
