'use client';

export interface DivergenceChipProps {
  gap: number;
  onClick?: () => void;
  className?: string;
}

/** Compact chip when street consensus and PMT Smart Bias disagree beyond threshold. */
export default function DivergenceChip({ gap, onClick, className }: DivergenceChipProps) {
  const label = `Δ${gap.toFixed(2)}`;
  return (
    <button
      type="button"
      data-divergence-chip="true"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      className={`inline-flex items-center rounded-none border border-warn/40 bg-warn/10 px-1.5 py-0.5 text-[10px] font-mono text-warn transition-colors hover:border-warn/60 hover:bg-warn/15${
        className ? ` ${className}` : ''
      }`}
      title="Street consensus and PMT Smart Bias disagree — click for both reads"
    >
      {label}
    </button>
  );
}
