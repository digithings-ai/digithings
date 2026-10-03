'use client';

import { useEffect, useRef, useState } from 'react';
import { getChartColors } from '@/lib/chart-colors';
import { VELA_PROJECT_URL, deskChartWheelAction, deskVelaOptions } from '@/lib/desk/vela-theme';
import type { VelaSpikeBar } from '@/components/research/VelaSpikeChart';
import { DeskState } from './DeskState';

export interface DeskChartProps {
  bars: readonly VelaSpikeBar[];
  /** Shown as data on the host. Brief panes pass the book symbol. */
  symbol?: string;
  timeframe?: string;
  hostTestId?: string;
  hostClassName?: string;
  emptyMessage?: string;
}

function paneScroller(host: HTMLElement): HTMLElement | null {
  const found = host.closest('[data-desk-pane-scroll]');
  if (found instanceof HTMLElement && found !== host) return found;
  return null;
}

/**
 * Price pane. Candles use digiquant teal and red. A vertical wheel scrolls
 * the pane column; a horizontal wheel is left to Vela.
 *
 * Vela is imported inside the effect so the static export does not evaluate
 * the chart runtime on the server.
 */
export function DeskChart({
  bars,
  symbol,
  timeframe = '1D',
  hostTestId = 'desk-chart-host',
  hostClassName = 'h-full min-h-[240px] w-full',
  emptyMessage = 'No bars',
}: DeskChartProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [mountError, setMountError] = useState<string | null>(null);
  const hasBars = bars.length > 0;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const onWheel = (event: WheelEvent) => {
      if (deskChartWheelAction(event) !== 'scroll-pane') return;
      const scroller = paneScroller(host);
      if (!scroller) return;
      event.preventDefault();
      event.stopPropagation();
      scroller.scrollTop += event.deltaY;
    };
    host.addEventListener('wheel', onWheel, { passive: false });
    return () => host.removeEventListener('wheel', onWheel);
  }, [hasBars]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !hasBars) return;
    let chart: { destroy(): void } | null = null;
    let cancelled = false;
    const colors = getChartColors();
    (async () => {
      try {
        const { Vela } = await import('@luxalgo/vela');
        if (cancelled || !hostRef.current) return;
        chart = new Vela(
          host,
          deskVelaOptions(bars, timeframe, {
            background: colors.bg,
            text: colors.ink,
            grid: colors.hair,
          }),
        );
      } catch (err) {
        if (!cancelled) setMountError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
      chart?.destroy();
      chart = null;
    };
  }, [bars, hasBars, timeframe]);

  if (bars.length === 0) {
    return (
      <div data-testid="desk-chart" data-symbol={symbol ?? ''}>
        <DeskState state="empty" emptyMessage={emptyMessage} />
      </div>
    );
  }

  return (
    <div data-testid="desk-chart" data-symbol={symbol ?? ''}>
      <div ref={hostRef} data-testid={hostTestId} className={hostClassName} />
      {mountError ? (
        <p className="px-3 py-1 font-mono text-[10px] text-warn" data-testid="desk-chart-mount-error">
          Vela failed to mount: {mountError}
        </p>
      ) : null}
      <p className="px-3 py-1 font-mono text-[10px] text-ink-mute" data-testid="desk-chart-attribution">
        Chart by{' '}
        <a href={VELA_PROJECT_URL} target="_blank" rel="noreferrer" className="underline">
          Vela (LuxAlgo)
        </a>
      </p>
    </div>
  );
}
