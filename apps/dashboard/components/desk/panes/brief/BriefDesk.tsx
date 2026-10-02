'use client';

import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import type { VelaTimeframe } from '@/lib/vela-bars';
import { BriefPaneContent } from './bodies';
import { loadBriefSnapshot } from './load';
import { buildBriefPanes, loadingBriefPanes, type BriefPaneView } from './model';

const SPAN: Record<number, string> = {
  4: 'col-span-12 md:col-span-4',
  5: 'col-span-12 md:col-span-5',
  7: 'col-span-12 md:col-span-7',
  8: 'col-span-12 md:col-span-8',
  12: 'col-span-12',
};

/** Desktop row tracks that fill one 12-row viewport. Narrow view stacks. */
const ROW: Record<string, string> = {
  decision: 'md:row-span-3',
  signals: 'md:row-span-3',
  allocation: 'md:row-span-3',
  movers: 'md:row-span-3',
  breaks: 'md:row-span-3',
  'gloomberg-quotes': 'md:row-span-2',
  'gloomberg-tape': 'md:row-span-2',
  luxalgo: 'md:row-span-2',
  run: 'md:row-span-2',
};

/**
 * Temporary frame until Slice A's `PaneFrame` mounts these models.
 * Shows the chrome path. Does not add fullscreen, drag, or a KPI hero.
 */
export function BriefPaneFrame({ pane, children }: { pane: BriefPaneView; children: ReactNode }) {
  const span = SPAN[pane.columns ?? 12] ?? 'col-span-12';
  const row = ROW[pane.id] ?? '';
  return (
    <section
      data-testid={`brief-pane-${pane.id}`}
      data-chrome-path={pane.chromePath}
      data-pane-state={pane.state}
      className={`flex min-h-[11rem] min-w-0 flex-col overflow-hidden border border-hair bg-surface md:min-h-0 ${span} ${row}`}
    >
      <header className="flex items-baseline gap-2 border-b border-hair px-3 py-2">
        <span className="font-mono text-[10px] text-ink-mute">{pane.eyebrow}</span>
        <h2 className="text-[11px] font-semibold uppercase tracking-widest">{pane.title}</h2>
        <span className="ml-auto font-mono text-[10px] text-ink-mute">{pane.chromePath}</span>
      </header>
      <div data-pane-scroll className="min-h-0 flex-1 overflow-auto">
        {children}
      </div>
    </section>
  );
}

export function BriefDeskView({
  panes,
  onTimeframe,
  retrievalPin,
}: {
  panes: BriefPaneView[];
  onTimeframe?: (timeframe: VelaTimeframe) => void;
  retrievalPin?: string | null;
}) {
  return (
    <div
      data-testid="brief-desk"
      data-retrieval-pin={retrievalPin ?? undefined}
      className="grid min-h-0 flex-1 grid-cols-12 content-start gap-px bg-hair md:h-full md:grid-rows-12 md:overflow-hidden"
    >
      {panes.map((pane) => (
        <BriefPaneFrame key={pane.id} pane={pane}>
          <BriefPaneContent pane={pane} onTimeframe={onTimeframe} />
        </BriefPaneFrame>
      ))}
    </div>
  );
}

/**
 * One-viewport Brief. Fills the app frame; each pane scrolls inside itself.
 * Slice A can keep `BRIEF_PANES` + `BriefPaneContent` and drop this grid
 * into `DeskShell` without rewriting the bodies.
 */
export function BriefDesk() {
  const [timeframe, setTimeframe] = useState<VelaTimeframe>('1d');
  const [panes, setPanes] = useState<BriefPaneView[]>(() => loadingBriefPanes('1d'));
  const [retrievalPin, setRetrievalPin] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void loadBriefSnapshot(timeframe).then((snapshot) => {
      if (cancelled) return;
      setPanes(buildBriefPanes(snapshot, timeframe));
      const pin =
        snapshot.brief.status === 'ok' ? (snapshot.brief.data?.retrievalPin ?? null) : null;
      setRetrievalPin(pin);
    });
    return () => {
      cancelled = true;
    };
  }, [timeframe]);

  function selectTimeframe(next: VelaTimeframe) {
    setTimeframe(next);
    setPanes(loadingBriefPanes(next));
    setRetrievalPin(null);
  }

  return (
    <BriefDeskView panes={panes} retrievalPin={retrievalPin} onTimeframe={selectTimeframe} />
  );
}
