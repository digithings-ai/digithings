'use client';

import { useEffect, useRef, useState } from 'react';

/** Vela project page — the attribution link target required by NOTICE.luxalgo-vela. */
export const VELA_PROJECT_URL = 'https://luxalgo.com/vela';

/** Pinned headless chart version this spike was built against. */
export const VELA_VERSION = '0.8.0';

/**
 * A single digiquant-owned bar. `t` is the bar open time in epoch
 * milliseconds; mirrors the spike spec `{t, o, h, l, c, v}` shape and maps
 * 1:1 onto Vela's offline `OHLCV` option (no provider, no network).
 */
export interface VelaSpikeBar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v?: number;
}

export interface VelaSpikeChartProps {
  bars: VelaSpikeBar[];
  symbol: string;
  timeframe?: string;
  /** Deep-link target for strategy work — the default; the embed is the spike. */
  quantChartsHref?: string;
}

function fmtDay(t: number): string {
  return new Date(t).toISOString().slice(0, 10);
}

/**
 * Read-only research-chart spike (#4830): renders digiquant-owned bars with
 * headless Vela core from the offline `data` option — no data provider, no
 * scripting engine, `live: false`, drawings toolbar hidden.
 *
 * The static markup (symbol caption, bar count, attribution) renders on the
 * server so the chart stays legible and testable without pixels; Vela itself
 * mounts client-side in an effect and is destroyed on unmount. The default
 * Vela watermark is left enabled AND an equivalent visible attribution is
 * shown on the same screen (NOTICE §ATTRIBUTION REQUIREMENT).
 */
export function VelaSpikeChart({
  bars,
  symbol,
  timeframe = '1D',
  quantChartsHref = 'https://app.luxalgo.com/',
}: VelaSpikeChartProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [mountError, setMountError] = useState<string | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || bars.length === 0) return;
    let chart: { destroy(): void } | null = null;
    let cancelled = false;
    (async () => {
      try {
        const { Vela } = await import('@luxalgo/vela');
        if (cancelled) return;
        chart = new Vela(host, {
          data: bars.map((b) => ({
            time: b.t,
            open: b.o,
            high: b.h,
            low: b.l,
            close: b.c,
            ...(b.v === undefined ? {} : { volume: b.v }),
          })),
          timeframe,
          theme: 'dark',
          live: false,
          drawings: false,
        });
      } catch (err) {
        if (!cancelled) setMountError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
      chart?.destroy();
      chart = null;
    };
  }, [bars, timeframe]);

  if (bars.length === 0) {
    return (
      <div
        className="border border-hair bg-surface/40 p-4 text-xs text-ink-mute"
        data-testid="vela-spike-chart"
      >
        No bars for {symbol} yet.
      </div>
    );
  }

  const first = bars[0];
  const last = bars[bars.length - 1];

  return (
    <div className="space-y-1.5" data-testid="vela-spike-chart">
      <p className="font-mono text-[11px] text-ink-soft">
        {symbol} · {timeframe} · {bars.length} bars · {fmtDay(first.t)}–{fmtDay(last.t)}
        {' · '}
        <span className="rounded border border-hair px-1 text-ink-mute">experimental</span>
      </p>
      <div ref={hostRef} data-testid="vela-spike-host" className="h-[320px] w-full" />
      {mountError ? (
        <p className="font-mono text-[10px] text-warn" data-testid="vela-spike-mount-error">
          Vela failed to mount: {mountError} — figures above are the underlying bars.
        </p>
      ) : null}
      <p className="font-mono text-[10px] text-ink-mute" data-testid="vela-attribution">
        Chart by{' '}
        <a href={VELA_PROJECT_URL} target="_blank" rel="noreferrer" className="underline">
          Vela (LuxAlgo)
        </a>{' '}
        · read-only research spike ·{' '}
        <a href={quantChartsHref} target="_blank" rel="noreferrer" className="underline">
          Open in QuantCharts
        </a>
      </p>
    </div>
  );
}

export default VelaSpikeChart;
