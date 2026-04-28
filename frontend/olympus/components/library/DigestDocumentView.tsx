'use client';

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { Change } from 'diff';
import { diffLines, diffWords } from 'diff';
import { ChevronDown, List } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  fetchDigestDiffContext,
  loadDigestLibraryDiff,
  type DigestCompareKind,
  type DigestDiffContext,
} from '@/lib/queries';

type ViewScope = 'current' | 'difference';
type DiffLayout = 'inline' | 'split';

type DigestTocEntry = { id: string; text: string; level: 2 | 3 };

function slugifyDigestHeading(s: string): string {
  const b = s
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 64);
  return b || 'section';
}

/** ## / ### headings only — used for jump nav and stable anchor ids. */
function buildDigestToc(markdown: string): DigestTocEntry[] {
  const lines = markdown.split(/\r?\n/);
  const slugCounts = new Map<string, number>();
  const out: DigestTocEntry[] = [];
  for (const line of lines) {
    const t = line.trim();
    const m = /^(#{2,3})\s+(.+)$/.exec(t);
    if (!m) continue;
    const level = (m[1].length === 2 ? 2 : 3) as 2 | 3;
    const text = m[2].trim();
    const base = slugifyDigestHeading(text);
    const n = (slugCounts.get(base) ?? 0) + 1;
    slugCounts.set(base, n);
    const id = n === 1 ? base : `${base}-${n}`;
    out.push({ id, text, level });
  }
  return out;
}

function isTableLine(s: string): boolean {
  const t = s.trimStart();
  return t.startsWith('|');
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

function comparePresetLabel(kind: 'previous_digest' | 'delta_baseline', ctx: DigestDiffContext | null): string {
  if (kind === 'delta_baseline') return ctx?.deltaBaselineDate ? `Delta baseline (${ctx.deltaBaselineDate})` : 'Delta baseline';
  return ctx?.previousDigestDate ? `Previous digest (${ctx.previousDigestDate})` : 'Previous digest';
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

function DigestCompareDropdown({
  context,
  compareKind,
  customCompareDate,
  canComparePrevious,
  canCompareBaseline,
  onSelectPreset,
}: {
  context: DigestDiffContext;
  compareKind: DigestCompareKind;
  customCompareDate: string;
  canComparePrevious: boolean;
  canCompareBaseline: boolean;
  onSelectPreset: (k: 'previous_digest' | 'delta_baseline') => void;
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
        ? comparePresetLabel('delta_baseline', context)
        : comparePresetLabel('previous_digest', context);

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
          <div role="listbox" aria-label="Compare digest to" className="max-h-52 overflow-y-auto py-1">
            <button
              type="button"
              role="option"
              aria-selected={compareKind === 'previous_digest' ? 'true' : 'false'}
              disabled={!canComparePrevious}
              onClick={() => {
                if (!canComparePrevious) return;
                onSelectPreset('previous_digest');
                setOpen(false);
              }}
              className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                !canComparePrevious
                  ? 'text-text-muted opacity-40 cursor-not-allowed'
                  : compareKind === 'previous_digest'
                    ? 'bg-fin-blue/15 text-fin-blue'
                    : 'text-text-secondary hover:bg-white/[0.06] hover:text-text-primary'
              }`}
            >
              {comparePresetLabel('previous_digest', context)}
            </button>
            <button
              type="button"
              role="option"
              aria-selected={compareKind === 'delta_baseline' ? 'true' : 'false'}
              disabled={!canCompareBaseline}
              onClick={() => {
                if (!canCompareBaseline) return;
                onSelectPreset('delta_baseline');
                setOpen(false);
              }}
              className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                !canCompareBaseline
                  ? 'text-text-muted opacity-40 cursor-not-allowed'
                  : compareKind === 'delta_baseline'
                    ? 'bg-fin-blue/15 text-fin-blue'
                    : 'text-text-secondary hover:bg-white/[0.06] hover:text-text-primary'
              }`}
            >
              {comparePresetLabel('delta_baseline', context)}
            </button>
          </div>
          <p className="text-[10px] text-text-muted px-2.5 py-1.5 border-t border-border-subtle bg-bg-secondary/80">
            Previous or baseline — or use the date field beside this menu for a custom snapshot.
          </p>
        </div>
      )}
    </div>
  );
}

export default function DigestDocumentView({
  docDate,
  fallbackMarkdown,
}: {
  docDate: string;
  fallbackMarkdown: string;
}) {
  const [viewScope, setViewScope] = useState<ViewScope>('current');
  const [diffLayout, setDiffLayout] = useState<DiffLayout>('inline');
  const [compareKind, setCompareKind] = useState<DigestCompareKind>('previous_digest');
  const [customCompareDate, setCustomCompareDate] = useState('');
  const [contextLoading, setContextLoading] = useState(true);
  const [pairLoading, setPairLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [context, setContext] = useState<DigestDiffContext | null>(null);
  const [pair, setPair] = useState<Awaited<ReturnType<typeof loadDigestLibraryDiff>>['pair']>(null);
  const preferPreviousRef = useRef(false);

  useEffect(() => {
    if (!preferPreviousRef.current || viewScope !== 'difference' || !context) return;
    preferPreviousRef.current = false;
    setCustomCompareDate('');
    if (context.previousDigestDate) setCompareKind('previous_digest');
    else if (context.deltaBaselineDate) setCompareKind('delta_baseline');
  }, [context, viewScope]);

  useEffect(() => {
    let cancelled = false;
    setContextLoading(true);
    setError(null);
    fetchDigestDiffContext(docDate)
      .then((ctx) => {
        if (!cancelled) setContext(ctx);
      })
      .catch((e) => {
        if (!cancelled) {
          setContext(null);
          setError(e instanceof Error ? e.message : 'Failed to load digest context');
        }
      })
      .finally(() => {
        if (!cancelled) setContextLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [docDate]);

  useEffect(() => {
    if (viewScope === 'current') return;
    let cancelled = false;
    setPairLoading(true);
    setError(null);
    const customArg = compareKind === 'custom_date' ? customCompareDate : undefined;
    loadDigestLibraryDiff(docDate, compareKind, customArg)
      .then(({ pair: p }) => {
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
  }, [docDate, compareKind, customCompareDate, viewScope]);

  const lineItems = useMemo(() => {
    if (!pair) return [];
    return lineDiffToItems(diffLines(pair.beforeMarkdown, pair.afterMarkdown));
  }, [pair]);

  const hasDiff = useMemo(() => lineItems.some((it) => it.kind !== 'equal'), [lineItems]);

  const canComparePrevious = !!context?.previousDigestDate;
  const canCompareBaseline = !!context?.deltaBaselineDate;
  const customReady = compareKind !== 'custom_date' || /^\d{4}-\d{2}-\d{2}$/.test(customCompareDate.trim());

  const digestToc = useMemo(() => buildDigestToc(fallbackMarkdown), [fallbackMarkdown]);

  const toolbar = context ? (
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
            <button
              type="button"
              className={segmentBtnClass(diffLayout === 'split')}
              onClick={() => setDiffLayout('split')}
            >
              Side by side
            </button>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
            <DigestCompareDropdown
              context={context}
              compareKind={compareKind}
              customCompareDate={customCompareDate}
              canComparePrevious={canComparePrevious}
              canCompareBaseline={canCompareBaseline}
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
                  else if (canComparePrevious) setCompareKind('previous_digest');
                  else if (canCompareBaseline) setCompareKind('delta_baseline');
                }}
                className="rounded-md border border-border-subtle bg-bg-secondary px-2 py-1.5 text-xs text-text-primary font-mono focus:outline-none focus:ring-1 focus:ring-inset focus:ring-fin-blue/30"
                aria-label="Compare digest to a custom snapshot date"
              />
            </label>
          </div>
        </>
      ) : null}

      {context.changeCount > 0 ? (
        <span className="text-text-muted text-xs sm:ml-auto">
          {context.changeCount} path{context.changeCount !== 1 ? 's' : ''} in delta-request
        </span>
      ) : null}
    </div>
  ) : null;

  if (contextLoading) {
    return <p className="text-text-muted text-sm">Loading digest…</p>;
  }

  if (error && !context) {
    return (
      <div className="space-y-3">
        <p className="text-fin-red text-xs">{error}</p>
        <div className="prose prose-invert max-w-none text-sm">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
        </div>
      </div>
    );
  }

  if (viewScope === 'current') {
    let mdPtr = 0;
    const mdComponents = {
      h2: (props: { children?: ReactNode; node?: unknown; className?: string }) => {
        const { node: _n, ...rest } = props;
        while (mdPtr < digestToc.length && digestToc[mdPtr].level !== 2) mdPtr += 1;
        const meta =
          mdPtr < digestToc.length && digestToc[mdPtr].level === 2 ? digestToc[mdPtr++] : null;
        return (
          <h2
            {...rest}
            id={meta?.id}
            className="scroll-mt-28 mt-8 first:mt-0 text-xl font-semibold text-text-primary border-b border-border-subtle/40 pb-1.5"
          />
        );
      },
      h3: (props: { children?: ReactNode; node?: unknown; className?: string }) => {
        const { node: _n, ...rest } = props;
        while (mdPtr < digestToc.length && digestToc[mdPtr].level !== 3) mdPtr += 1;
        const meta =
          mdPtr < digestToc.length && digestToc[mdPtr].level === 3 ? digestToc[mdPtr++] : null;
        return (
          <h3
            {...rest}
            id={meta?.id}
            className="scroll-mt-24 mt-5 text-base font-semibold text-text-secondary"
          />
        );
      },
    };

    return (
      <div className="space-y-4">
        {toolbar}
        {digestToc.length > 0 ? (
          <nav
            aria-label="Digest sections"
            className="rounded-lg border border-border-subtle bg-bg-secondary/50 px-3 py-2.5"
          >
            <div className="flex items-center gap-2 mb-2">
              <List size={14} className="text-fin-blue shrink-0" aria-hidden />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Jump to section</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {digestToc.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => {
                    const el = document.getElementById(t.id);
                    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                  }}
                  className={`text-left text-xs px-2 py-1 rounded-md border transition-colors max-w-[min(100%,14rem)] truncate ${
                    t.level === 3
                      ? 'border-border-subtle/70 bg-bg-secondary/80 text-text-muted hover:border-fin-blue/35'
                      : 'border-border-subtle bg-bg-secondary text-text-secondary hover:border-fin-blue/40 hover:text-text-primary'
                  }`}
                  title={t.text}
                >
                  {t.text}
                </button>
              ))}
            </div>
          </nav>
        ) : null}
        <div className="prose prose-invert max-w-none text-sm leading-relaxed">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {fallbackMarkdown}
          </ReactMarkdown>
        </div>
      </div>
    );
  }

  if (!customReady) {
    return (
      <div className="space-y-4">
        {toolbar}
        <p className="text-text-muted text-sm">Choose a snapshot date to compare.</p>
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
          {compareKind === 'delta_baseline' && canCompareBaseline
            ? 'Could not load snapshots for the delta baseline date, or the current digest is empty.'
            : compareKind === 'custom_date'
              ? 'No digest snapshot for that date, or the current digest is empty.'
              : compareKind === 'previous_digest' && canComparePrevious
                ? 'Could not load markdown for the prior snapshot or this date (check daily_snapshots).'
                : 'No comparison snapshot available for this choice.'}
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
      <p className="text-text-muted text-[11px]">
        Showing diff vs <span className="font-mono text-fin-blue">{pair.compareDate}</span>
        {pair.changeCount > 0 ? (
          <span>
            {' '}
            · {pair.changeCount} path{pair.changeCount !== 1 ? 's' : ''} in delta-request
          </span>
        ) : null}
      </p>

      {diffLayout === 'inline' ? (
        <div>
          {!hasDiff ? (
            <p className="text-text-muted text-sm mb-3">No text changes vs comparison snapshot.</p>
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
