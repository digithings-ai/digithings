'use client';

import { StatTile } from '@/components/observability/shared';
import type { AtlasRunDiagnostics } from '@/lib/types';

export function formatUsd(n: number | null): string {
  if (n == null || Number.isNaN(n)) return '—';
  return `$${n.toFixed(2)}`;
}

export function formatTokens(n: number | null): string {
  if (n == null || Number.isNaN(n)) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return `${n}`;
}

/** Whole-percent cache-hit, or null when total tokens are unknown. */
export function cacheHitPct(d: AtlasRunDiagnostics): number | null {
  if (d.total_tokens == null || d.total_tokens === 0) return null;
  return Math.round(((d.cached_tokens ?? 0) / d.total_tokens) * 100);
}

export function RunEconomicsRow({ latest }: { latest: AtlasRunDiagnostics }) {
  const cache = cacheHitPct(latest);
  const grounding =
    latest.grounding_ok != null
      ? `${latest.grounding_ok}/${(latest.grounding_ok ?? 0) + (latest.grounding_failed ?? 0)}`
      : '—';
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatTile label="Cost / run" value={formatUsd(latest.est_cost_usd)} />
      <StatTile
        label="Tokens"
        value={formatTokens(latest.total_tokens)}
        sub={
          cache != null ? (
            <span className="text-[var(--accent)]">{cache}% cached → cheaper</span>
          ) : undefined
        }
      />
      <StatTile label="LLM calls" value={latest.llm_calls != null ? latest.llm_calls : '—'} />
      <StatTile
        label="Grounding"
        value={grounding}
        color={(latest.grounding_failed ?? 0) > 0 ? 'text-fin-amber' : undefined}
      />
    </div>
  );
}
