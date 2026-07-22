'use client';

import { TrendingDown, TrendingUp } from 'lucide-react';
import type { AnalystPayload } from '@/lib/types';

/**
 * Renders the full H5 analyst payload (#1562 PR2, #1615 flat editorial workspace)
 * — every section the blueprint names, keyed off the exact backend field names
 * (`digiquant/.../hermes/models/analyst.py:AnalystPayload`).
 *
 * Flat hairline-led editorial workspace (#1615): thesis/current call prominent,
 * bull/bear and tailwind/headwind evidence in deliberate columns. NOT a glass-card.
 *
 * Canon: `--up`/`--down` are reserved for realized P&L / signed conviction
 * values (SignedConvictionBadge, pnlColor) — tailwinds/headwinds are qualitative
 * factors, not money, so they're told apart by icon shape (Trending Up/Down) in
 * neutral ink, not by borrowing the money palette.
 */

function Kicker({ children }: { children: string }) {
  return (
    <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
      {children}
    </h3>
  );
}

function ProseSection({ title, text }: { title: string; text: string }) {
  if (!text.trim()) return null;
  return (
    <section className="space-y-2">
      <Kicker>{title}</Kicker>
      <p className="text-sm leading-relaxed text-ink-soft">{text}</p>
    </section>
  );
}

function WindList({
  title,
  items,
  icon: Icon,
}: {
  title: string;
  items: string[];
  icon: typeof TrendingUp;
}) {
  return (
    <section className="space-y-2">
      <Kicker>{title}</Kicker>
      {items.length === 0 ? (
        <p className="text-xs text-ink-mute">None recorded.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-2 text-sm leading-relaxed text-ink-soft">
              <Icon size={14} className="mt-0.5 shrink-0 text-ink-mute" aria-hidden />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Free-form label→value dict (keys vary call to call) rendered as a stat strip. */
function PriceTargets({ targets }: { targets: Record<string, number | string> | null }) {
  if (!targets) return null;
  const entries = Object.entries(targets).filter(([, v]) => v != null);
  if (entries.length === 0) return null;
  return (
    <section className="space-y-2">
      <Kicker>Price targets</Kicker>
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        {entries.map(([label, value]) => (
          <div key={label} className="flex flex-col gap-0.5">
            <span className="text-xs uppercase tracking-wider text-ink-mute">
              {label.replace(/_/g, ' ')}
            </span>
            <span className="font-mono text-sm tabular-nums text-ink">
              {typeof value === 'number' ? value.toLocaleString('en-US') : String(value)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function References({ sources }: { sources: string[] }) {
  if (sources.length === 0) return null;
  return (
    <section className="space-y-2">
      <Kicker>References</Kicker>
      <ul className="list-disc space-y-1 pl-5 text-xs text-ink-soft">
        {sources.map((url, i) => (
          <li key={i} className="truncate">
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              {url}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function AnalystDossierCard({
  payload,
  asOf,
}: {
  payload: AnalystPayload;
  asOf: string | null;
}) {
  return (
    <div className="analyst-workspace space-y-0 bg-surface/[0.82] py-6">
      <div className="space-y-6 px-5 md:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hair pb-4">
          <h2 className="font-display text-lg text-ink">Research argument</h2>
          {asOf && (
            <span className="font-mono text-[0.65rem] uppercase tracking-wider text-accent">
              {asOf}
            </span>
          )}
        </div>

        {/* Thesis — prominent main argument */}
        <ProseSection title="Thesis" text={payload.thesis} />

        {/* Bull/Bear cases — deliberate 2-column grid */}
        {(payload.bull_case.trim() || payload.bear_case.trim()) && (
          <div className="grid gap-6 border-t border-hair pt-6 md:grid-cols-2">
            <ProseSection title="Bull case" text={payload.bull_case} />
            <ProseSection title="Bear case" text={payload.bear_case} />
          </div>
        )}

        {/* Tailwinds/Headwinds — deliberate 2-column grid, neutral styling */}
        <div className="grid gap-6 border-t border-hair pt-6 md:grid-cols-2">
          <WindList title="Tailwinds" items={payload.tailwinds} icon={TrendingUp} />
          <WindList title="Headwinds" items={payload.headwinds} icon={TrendingDown} />
        </div>

        {/* Risks — full-width */}
        {payload.risks.trim() && (
          <div className="border-t border-hair pt-6">
            <ProseSection title="Risks" text={payload.risks} />
          </div>
        )}

        {/* Technicals / Expectations / Fundamentals — 3-column grid */}
        {(payload.technicals.trim() ||
          payload.expectations.trim() ||
          payload.fundamentals.trim()) && (
          <div className="grid gap-6 border-t border-hair pt-6 md:grid-cols-3">
            <ProseSection title="Technicals" text={payload.technicals} />
            <ProseSection title="Expectations" text={payload.expectations} />
            <ProseSection title="Fundamentals" text={payload.fundamentals} />
          </div>
        )}

        {/* Price targets — inline metrics */}
        {payload.price_targets && (
          <div className="border-t border-hair pt-6">
            <PriceTargets targets={payload.price_targets} />
          </div>
        )}

        {/* References — footer */}
        {payload.sources.length > 0 && (
          <div className="border-t border-hair pt-6">
            <References sources={payload.sources} />
          </div>
        )}
      </div>
    </div>
  );
}
