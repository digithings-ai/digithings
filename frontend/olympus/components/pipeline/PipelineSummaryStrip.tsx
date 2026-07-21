import { Skeleton } from '@digithings/web';
import type { RegimeChip, RegimeChipColor } from '@/lib/render-pipeline-payloads';

export type { RegimeChip, RegimeChipColor };

export interface PipelineSummaryStripProps {
  headline: string | null;
  regimeChips: RegimeChip[];
  /** The decision summary string (e.g. "4 holdings · 75% invested") */
  decision: string | null;
  /** Day queries in flight — render a skeleton, not headline-styled placeholder text. */
  loading?: boolean;
}

const DOT_COLOR: Record<RegimeChipColor, string> = {
  green: 'bg-accent',
  red: 'bg-warn',
  amber: 'bg-warn',
  blue: 'bg-accent',
  muted: 'bg-hair',
};

export default function PipelineSummaryStrip({
  headline,
  regimeChips,
  decision,
  loading = false,
}: PipelineSummaryStripProps) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-3">
      {/* Digest headline — absorbs "The Read" */}
      <div className="flex-1 min-w-[230px] font-display" aria-busy={loading || undefined}>
        <span className="mb-0.5 block font-sans text-xs font-bold uppercase text-accent">
          The read
        </span>
        {headline ? (
          <span className="text-sm leading-snug text-ink">{headline}</span>
        ) : loading ? (
          // Skeleton bar — a placeholder must not wear the exact type style
          // of a real headline. sk shimmer per the #1548 one-grammar ruling.
          <Skeleton className="block h-4 max-w-[420px]" />
        ) : (
          <span className="text-sm leading-snug text-ink-mute">
            No digest for this day
          </span>
        )}
      </div>

      {/* Regime chips + decision */}
      <div className="flex gap-1.5 flex-wrap items-center">
        {regimeChips.map((chip) => (
          <span
            key={`${chip.label}-${chip.value}`}
            className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border border-hair bg-term-bg px-2 py-1 text-xs text-ink-mute"
          >
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${DOT_COLOR[chip.color]}`} />
            {chip.label}{' '}
            <strong className="text-ink font-semibold">{chip.value}</strong>
          </span>
        ))}

        {decision && (
          <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border border-hair bg-term-bg px-2 py-1 text-xs text-ink-mute">
            {/* Status pip — calm cyan chrome (F5), not up */}
            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-accent" />
            Decision{' '}
            <strong className="text-ink font-semibold">{decision}</strong>
          </span>
        )}
      </div>
    </div>
  );
}
