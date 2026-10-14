'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import PageSkeleton from '@/components/page-skeleton';
import VelaSpikeChart from '@/components/research/VelaSpikeChart';
import {
  VelaBarsError,
  fetchVelaBars,
  normalizeVelaSymbol,
  normalizeVelaTimeframe,
  type VelaBarsResult,
} from '@/lib/vela-bars';

/**
 * Vela read-only research chart (#4830 spike, #4879 full-chart wiring).
 *
 * Fetching component: `?symbol=<listing>` (default `BTC-USD`) and
 * `?timeframe=<tf>` (default `1d`) select the bars, served keyless from
 * digiquant `GET /bars` (anonymous Gloomberb price history — no keys, no
 * session cookie, display-only). Loading / empty / error states render
 * inline; the chart itself mounts headless Vela core from the offline
 * `data` option (no provider, no Pine scripting, no SaaS calls). Strategy
 * work still defaults to the QuantCharts deep-link.
 *
 * Client-rendered under a static export (`output: 'export'`), so params
 * come from `useSearchParams` and bars load in an effect — there is no
 * request-time server fetch on this route.
 */

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; result: VelaBarsResult }
  | { status: 'error'; message: string };

function VelaSpikePageInner({ symbol, timeframe }: { symbol: string; timeframe: string }) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [retryNonce, setRetryNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchVelaBars(symbol, timeframe, { signal: controller.signal }).then(
      (result) => {
        if (!controller.signal.aborted) setState({ status: 'ready', result });
      },
      (err) => {
        if (controller.signal.aborted) return;
        setState({
          status: 'error',
          message:
            err instanceof VelaBarsError
              ? err.message
              : err instanceof Error
                ? err.message
                : String(err),
        });
      }
    );
    return () => controller.abort();
  }, [symbol, timeframe, retryNonce]);

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <div className="space-y-1">
        <h1 className="text-lg font-semibold">Vela read-only research chart</h1>
        <p className="font-mono text-[11px] text-ink-mute">
          #4879 · {symbol} · {timeframe} · headless Vela core on digiquant-owned bars · read-only
          · no Pine scripting · no SaaS calls
        </p>
      </div>
      {state.status === 'loading' ? (
        <div
          className="border border-hair bg-surface/40 p-4 text-xs text-ink-mute"
          data-testid="vela-spike-loading"
          role="status"
        >
          Loading {symbol} {timeframe} bars…
        </div>
      ) : null}
      {state.status === 'error' ? (
        <div
          className="border border-hair bg-surface/40 p-4 text-xs text-warn"
          data-testid="vela-spike-error"
          role="alert"
        >
          <p>Couldn&apos;t load {symbol} bars: {state.message}</p>
          <button
            type="button"
            className="mt-2 rounded border border-hair px-2 py-1 font-mono text-[11px] text-ink-soft"
            onClick={() => setRetryNonce((n) => n + 1)}
          >
            Retry
          </button>
        </div>
      ) : null}
      {state.status === 'ready' ? (
        <>
          <VelaSpikeChart
            bars={state.result.bars}
            symbol={state.result.symbol}
            timeframe={state.result.timeframe}
          />
          <p className="font-mono text-[10px] text-ink-mute" data-testid="vela-spike-source">
            Bars: digiquant GET /bars · Sourced from Gloomberb
            {state.result.delayNote ? ` · ${state.result.delayNote}` : ''}
            {state.result.stale ? ' · upstream cache stale' : ''} · display only, never a
            backtest input.
          </p>
        </>
      ) : null}
      <p className="font-mono text-[10px] text-ink-mute">
        Compliance: Apache-2.0 LICENSE + Vela NOTICE ship with the dashboard
        (LICENSE.luxalgo-vela, NOTICE.luxalgo-vela); attribution stays visible on this screen.
      </p>
    </main>
  );
}

function VelaSpikeRoute() {
  const searchParams = useSearchParams();
  const symbol = normalizeVelaSymbol(searchParams.get('symbol'));
  const timeframe = normalizeVelaTimeframe(searchParams.get('timeframe'));
  // Remount on param change so the fetch state resets to loading without a
  // synchronous setState-in-effect (react-hooks/set-state-in-effect).
  return <VelaSpikePageInner key={`${symbol}:${timeframe}`} symbol={symbol} timeframe={timeframe} />;
}

export default function VelaSpikePage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <VelaSpikeRoute />
    </Suspense>
  );
}
