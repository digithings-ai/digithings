'use client';

import type { ReactNode } from 'react';
import { Button } from '@digithings/ui/ui';
import { DeskChart } from '@/components/desk/atoms/DeskChart';
import { DeskState } from '@/components/desk/atoms/DeskState';
import { VELA_TIMEFRAMES, type VelaTimeframe } from '@/lib/vela-bars';
import type { BriefPaneView } from './model';
import {
  GLOOMBERG_NO_CLOSES,
  GLOOMBERG_NO_TAPE,
} from './format';

function toneClass(tone: 'up' | 'down' | 'flat'): string {
  if (tone === 'up') return 'text-up';
  if (tone === 'down') return 'text-down';
  return 'text-ink';
}

function BriefTable({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-xs">{children}</table>
    </div>
  );
}

/**
 * Pane body only. Slice A mounts these inside `PaneFrame`; this module does
 * not draw the shell rail, path chrome, or a page-level KPI strip.
 */
export function BriefPaneContent({
  pane,
  onTimeframe,
}: {
  pane: BriefPaneView;
  onTimeframe?: (timeframe: VelaTimeframe) => void;
}) {
  const body = pane.body;
  switch (body.kind) {
    case 'decision':
      return (
        <DeskState state={pane.state} errorMessage={pane.errorMessage}>
          <div className="space-y-3 px-3 py-3">
            <p data-testid="brief-provenance" className="font-mono text-[10px] uppercase tracking-wider text-ink-mute">
              {body.badge}
            </p>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
              <div>
                <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Book</dt>
                <dd className="font-mono text-sm">{body.bookAsOf}</dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Day</dt>
                <dd data-testid="brief-decision-day" className="font-mono text-sm">{body.day}</dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Since inception</dt>
                <dd data-testid="brief-decision-since" className="font-mono text-sm">
                  {body.since}
                  <span className="mt-0.5 block text-[10px] text-ink-mute">{body.sinceStart}</span>
                </dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Invested</dt>
                <dd className="font-mono text-sm">{body.invested}</dd>
              </div>
            </dl>
            {body.events.length === 0 ? (
              <p className="text-xs text-ink-mute">No session events for this book date.</p>
            ) : (
              <ul className="space-y-1 text-xs">
                {body.events.map((event) => (
                  <li key={`${event.ticker}-${event.event}-${event.detail}`}>
                    <span className="font-mono">{event.ticker}</span> {event.event}
                    <span className="text-ink-mute"> · {event.detail}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </DeskState>
      );
    case 'signals':
      return (
        <DeskState state={pane.state} errorMessage={pane.errorMessage}>
          <BriefTable>
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-ink-mute">
                <th className="px-3 py-2 font-medium">Thesis</th>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">State</th>
                <th className="px-3 py-2 font-medium">Note</th>
              </tr>
            </thead>
            <tbody>
              {body.rows.map((row) => (
                <tr key={row.key} className="border-t border-hair">
                  <td className="px-3 py-2 font-mono">{row.id}</td>
                  <td className="px-3 py-2">{row.name}</td>
                  <td className="px-3 py-2">{row.state}</td>
                  <td className="px-3 py-2 text-ink-mute">{row.note}</td>
                </tr>
              ))}
            </tbody>
          </BriefTable>
        </DeskState>
      );
    case 'allocation':
      return (
        <DeskState state={pane.state} errorMessage={pane.errorMessage}>
          <div className="px-3 py-2 text-[10px] uppercase tracking-widest text-ink-mute">
            {body.nameCount} names · cash {body.cash} · invested {body.invested}
          </div>
          <BriefTable>
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-ink-mute">
                <th className="px-3 py-2 font-medium">Ticker</th>
                <th className="px-3 py-2 text-right font-medium">Weight</th>
              </tr>
            </thead>
            <tbody>
              {body.rows.map((row) => (
                <tr key={row.ticker} className="border-t border-hair">
                  <td className="px-3 py-2 font-mono">{row.ticker}</td>
                  <td className="px-3 py-2 text-right font-mono">{row.weight}</td>
                </tr>
              ))}
              <tr className="border-t border-hair">
                <td className="px-3 py-2">Cash</td>
                <td className="px-3 py-2 text-right font-mono">{body.cash}</td>
              </tr>
            </tbody>
          </BriefTable>
        </DeskState>
      );
    case 'movers':
      return (
        <DeskState state={pane.state} errorMessage={pane.errorMessage}>
          <p className="px-3 pt-2 text-[10px] text-ink-mute">
            Client-derived from allocations and market closes.
          </p>
          <BriefTable>
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-ink-mute">
                <th className="px-3 py-2 font-medium">Ticker</th>
                <th className="px-3 py-2 text-right font-medium">Mark</th>
                <th className="px-3 py-2 text-right font-medium">Day</th>
              </tr>
            </thead>
            <tbody>
              {body.rows.map((row) => (
                <tr key={row.ticker} className="border-t border-hair" data-testid={`mover-${row.ticker}`}>
                  <td className="px-3 py-2 font-mono">{row.ticker}</td>
                  <td className="px-3 py-2 text-right font-mono">{row.mark}</td>
                  <td className={`px-3 py-2 text-right font-mono ${toneClass(row.tone)}`}>{row.day}</td>
                </tr>
              ))}
            </tbody>
          </BriefTable>
        </DeskState>
      );
    case 'breaks':
      return (
        <DeskState state={pane.state} errorMessage={pane.errorMessage} emptyMessage={pane.emptyLabel}>
          <ul className="space-y-2 px-3 py-3 text-xs">
            {body.lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </DeskState>
      );
    case 'gloomberg-quotes':
      return (
        <div className="px-3 py-3 text-xs">
          {pane.state !== 'ready' ? (
            <p className="text-ink-mute">{GLOOMBERG_NO_CLOSES}</p>
          ) : null}
          <DeskState state={pane.state} errorMessage={pane.errorMessage}>
            <BriefTable>
              <thead>
                <tr className="text-[10px] uppercase tracking-widest text-ink-mute">
                  <th className="px-3 py-2 font-medium">Symbol</th>
                  <th className="px-3 py-2 text-right font-medium">Mark</th>
                </tr>
              </thead>
              <tbody>
                {body.marks.map((row) => (
                  <tr key={row.ticker} className="border-t border-hair">
                    <td className="px-3 py-2 font-mono">{row.ticker}</td>
                    <td className="px-3 py-2 text-right font-mono">{row.mark}</td>
                  </tr>
                ))}
              </tbody>
            </BriefTable>
            <p className="mt-2 text-[10px] text-ink-mute">House marks from the book. Not a Gloomberg feed.</p>
          </DeskState>
        </div>
      );
    case 'gloomberg-tape':
      return (
        <div className="px-3 py-3 text-xs">
          <p data-testid="gloomberg-tape-empty" className="text-ink-mute">
            {GLOOMBERG_NO_TAPE}
          </p>
          <DeskState state={pane.state} errorMessage={pane.errorMessage} />
        </div>
      );
    case 'luxalgo':
      return (
        <div>
          <div className="flex flex-wrap gap-1 px-3 pt-2">
            {VELA_TIMEFRAMES.map((tf) => (
              <Button
                key={tf}
                type="button"
                size="xs"
                variant={tf === body.timeframe ? 'outline' : 'ghost'}
                aria-current={tf === body.timeframe ? 'true' : undefined}
                onClick={() => onTimeframe?.(tf)}
              >
                {tf}
              </Button>
            ))}
          </div>
          <p className="px-3 pt-2 text-[10px] text-ink-mute">
            Display-only. Bars do not feed validate, backtest, optimize, or export.
          </p>
          {body.delayNote ? <p className="px-3 text-[10px] text-ink-mute">{body.delayNote}</p> : null}
          <DeskState state={pane.state} errorMessage={pane.errorMessage} emptyMessage={pane.emptyLabel}>
            <DeskChart bars={body.bars} symbol={body.symbol ?? ''} timeframe={body.timeframe} />
          </DeskState>
        </div>
      );
    case 'run':
      return (
        <DeskState state={pane.state} errorMessage={pane.errorMessage}>
          <dl className="flex flex-wrap gap-x-4 gap-y-2 px-3 py-3 font-mono text-xs">
            <div>
              <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Run</dt>
              <dd>{body.date}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Type</dt>
              <dd>{body.runType}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Status</dt>
              <dd>{body.status}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Nodes</dt>
              <dd>{body.segments}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Trace</dt>
              <dd>{body.trace}</dd>
            </div>
          </dl>
        </DeskState>
      );
    default: {
      const unknown: never = body;
      return unknown;
    }
  }
}
