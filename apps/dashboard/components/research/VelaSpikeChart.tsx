'use client';

import { DeskChart } from '@/components/desk/atoms/DeskChart';

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
      </p>
      <DeskChart
        bars={bars}
        timeframe={timeframe}
        hostTestId="vela-spike-host"
        hostClassName="h-[320px] w-full"
      />
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
