import type { RegimeChip, RegimeChipColor } from '@/lib/render-pipeline-payloads';

export type { RegimeChip, RegimeChipColor };

export interface PipelineSummaryStripProps {
  headline: string | null;
  regimeChips: RegimeChip[];
  /** The decision summary string (e.g. "4 holdings · 75% invested") */
  decision: string | null;
}

const DOT_COLOR: Record<RegimeChipColor, string> = {
  green: 'bg-fin-green',
  red: 'bg-fin-red',
  amber: 'bg-fin-amber',
  blue: 'bg-fin-blue',
  muted: 'bg-border-subtle',
};

export default function PipelineSummaryStrip({
  headline,
  regimeChips,
  decision,
}: PipelineSummaryStripProps) {
  return (
    <div className="flex gap-3 items-start flex-wrap mt-2.5">
      {/* Digest headline — absorbs "The Read" */}
      <div className="flex-1 min-w-[230px] font-display">
        <span className="block text-[9px] font-bold tracking-[0.14em] uppercase text-fin-blue mb-0.5 font-sans">
          The read
        </span>
        <span className="text-[14.5px] leading-snug text-text-primary">
          {headline ?? 'Loading digest…'}
        </span>
      </div>

      {/* Regime chips + decision */}
      <div className="flex gap-1.5 flex-wrap items-center">
        {regimeChips.map((chip) => (
          <span
            key={`${chip.label}-${chip.value}`}
            className="inline-flex items-center gap-1.5 text-[11px] bg-bg-secondary border border-border-subtle rounded-[7px] px-2 py-1 text-text-muted whitespace-nowrap"
          >
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${DOT_COLOR[chip.color]}`} />
            {chip.label}{' '}
            <strong className="text-text-primary font-semibold">{chip.value}</strong>
          </span>
        ))}

        {decision && (
          <span className="inline-flex items-center gap-1.5 text-[11px] bg-bg-secondary border border-border-subtle rounded-[7px] px-2 py-1 text-text-muted whitespace-nowrap">
            {/* Status pip — calm cyan chrome (F5), not fin-green */}
            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-fin-blue" />
            Decision{' '}
            <strong className="text-text-primary font-semibold">{decision}</strong>
          </span>
        )}
      </div>
    </div>
  );
}
