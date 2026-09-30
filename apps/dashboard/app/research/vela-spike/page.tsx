import VelaSpikeChart, { type VelaSpikeBar } from '@/components/research/VelaSpikeChart';

/**
 * Experimental read-only research-chart spike (#4830, epic #4779).
 *
 * Renders digiquant-owned bars with headless Vela core (`@luxalgo/vela`,
 * offline `data` option — no provider, no scripting engine, no SaaS calls).
 * The bars below are a canned deterministic fixture standing in for
 * digiquant-owned daily bars; strategy work still defaults to the QuantCharts
 * deep-link. Time-boxed spike: if the embed earns its keep, a follow-up wires
 * a real digiquant bar endpoint.
 */
function cannedFixtureBars(): VelaSpikeBar[] {
  const start = Date.UTC(2026, 7, 1); // 2026-08-01
  const closes = [
    100, 102, 101, 104, 103, 106, 105, 108, 107, 110, 109, 111, 108, 112, 114,
    113, 115, 114, 116, 118, 117, 119, 121, 120, 122, 121, 123, 125, 124, 126,
  ];
  return closes.map((c, i) => {
    const o = i === 0 ? 99 : closes[i - 1];
    return {
      t: start + i * 86_400_000,
      o,
      h: Math.max(o, c) + 1,
      l: Math.min(o, c) - 1,
      c,
      v: 1000 + i * 25,
    };
  });
}

export default function VelaSpikePage() {
  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <div className="space-y-1">
        <h1 className="text-lg font-semibold">Vela read-only research chart (experimental spike)</h1>
        <p className="font-mono text-[11px] text-ink-mute">
          #4830 · headless Vela core on digiquant-owned bars · read-only · no Pine scripting · no
          SaaS calls
        </p>
      </div>
      <VelaSpikeChart bars={cannedFixtureBars()} symbol="RESEARCH/BTCUSDT" timeframe="1D" />
      <p className="font-mono text-[10px] text-ink-mute">
        Bars above are a canned spike fixture. Compliance: Apache-2.0 LICENSE + Vela NOTICE ship
        with the dashboard (LICENSE.luxalgo-vela, NOTICE.luxalgo-vela); attribution stays visible
        on this screen.
      </p>
    </main>
  );
}
