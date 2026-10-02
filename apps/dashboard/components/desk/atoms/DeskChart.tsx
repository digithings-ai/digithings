'use client';

/**
 * TODO(slice-b): replace with Slice B's `DeskChart`. This mount exists so
 * the LuxAlgo pane can draw digiquant bars before that atom lands.
 * Colors are explicit (`upColor` / `downColor` plus a `VelaTheme` object).
 * `theme: 'dark'` is not the color source — stock green/red must not ship.
 */
import { useEffect, useRef, useState } from 'react';
import { getChartColors } from '@/lib/chart-colors';
import { dominantVerticalWheel } from './chart-wheel';

export interface DeskChartBar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v?: number;
}

const EMPTY_OHLC = 'O —  H —  L —  C —';

export function DeskChart({
  bars,
  symbol,
  timeframe = '1d',
}: {
  bars: DeskChartBar[];
  symbol: string;
  timeframe?: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [mountError, setMountError] = useState<string | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || bars.length === 0) return;
    let chart: { destroy(): void } | null = null;
    let cancelled = false;

    const onWheel = (event: WheelEvent) => {
      if (!dominantVerticalWheel(event.deltaX, event.deltaY)) return;
      const scroller = host.closest('[data-pane-scroll]');
      if (!(scroller instanceof HTMLElement)) return;
      event.preventDefault();
      scroller.scrollTop += event.deltaY;
    };
    host.addEventListener('wheel', onWheel, { passive: false });

    (async () => {
      try {
        const { Vela } = await import('@luxalgo/vela');
        if (cancelled) return;
        const colors = getChartColors();
        chart = new Vela(host, {
          data: bars.map((bar) => ({
            time: bar.t,
            open: bar.o,
            high: bar.h,
            low: bar.l,
            close: bar.c,
            ...(bar.v === undefined ? {} : { volume: bar.v }),
          })),
          timeframe,
          live: false,
          drawings: false,
          animations: { intro: false },
          nativeBackend: 'canvas2d',
          upColor: colors.up,
          downColor: colors.down,
          theme: {
            background: colors.bg,
            textColor: colors.ink,
            gridColor: colors.hair,
            borderColor: colors.hair,
            upColor: colors.up,
            downColor: colors.down,
            fontFamily: 'ui-monospace, monospace',
          },
        });
        setMountError(null);
      } catch (err) {
        if (!cancelled) {
          setMountError(err instanceof Error ? err.message : 'Chart failed to mount.');
        }
      }
    })();

    return () => {
      cancelled = true;
      host.removeEventListener('wheel', onWheel);
      chart?.destroy();
    };
  }, [bars, timeframe]);

  if (bars.length === 0) {
    return (
      <div data-testid="desk-chart-empty" className="px-3 py-3 text-xs text-ink-mute">
        <p>No series is drawn in this state.</p>
        <p className="mt-2 font-mono">{EMPTY_OHLC}</p>
        {symbol ? <p className="mt-2 font-mono text-ink">{symbol}</p> : null}
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-col">
      <p className="px-3 pt-2 font-mono text-[10px] text-ink-mute">
        digiquant bars · {symbol} · {timeframe} · not a LuxAlgo feed
      </p>
      {mountError ? (
        <p data-testid="desk-chart-error" className="px-3 py-2 text-xs text-ink-mute">
          {mountError}
        </p>
      ) : null}
      <div ref={hostRef} data-testid="desk-chart-host" className="min-h-[220px] w-full" />
    </div>
  );
}
