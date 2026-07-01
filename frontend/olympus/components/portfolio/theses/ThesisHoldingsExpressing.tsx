'use client';

import Link from 'next/link';
import type { Position } from '@/lib/types';
import { ConvictionMeter } from '@/components/shared/conviction-meter';

export function ThesisHoldingsExpressing({ positions }: { positions: Position[] }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
        Holdings expressing this thesis
      </h2>
      {positions.length === 0 ? (
        <p className="text-sm text-text-muted">No current holdings are tagged to this thesis.</p>
      ) : (
        <div className="glass-card divide-y divide-border-subtle overflow-hidden p-0">
          {positions.map((p) => (
            <Link
              key={p.ticker}
              href={`/portfolio?ticker=${encodeURIComponent(p.ticker)}`}
              className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
            >
              <span className="w-16 shrink-0 font-mono text-sm font-semibold text-text-primary">
                {p.ticker}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm text-text-secondary" title={p.name}>
                {p.name}
              </span>
              {p.conviction != null ? (
                <ConvictionMeter value={p.conviction} max={3} srLabel={`conviction ${p.conviction} of 3`} />
              ) : null}
              <span className="w-16 shrink-0 text-right font-mono text-sm tabular-nums text-text-primary">
                {p.weight_actual.toFixed(1)}%
              </span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
