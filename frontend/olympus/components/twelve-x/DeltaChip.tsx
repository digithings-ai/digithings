'use client';

/** A compact run-over-run delta glyph (or a "NEW" badge when there's no prior). */
export interface DeltaChipProps {
  delta: number | null;
  decimals?: number;
  isNew?: boolean;
  className?: string;
}

export default function DeltaChip({ delta, decimals = 2, isNew, className }: DeltaChipProps) {
  if (delta == null && !isNew) return null;

  if (isNew) {
    return (
      <span
        className={`text-[10px] rounded bg-accent/15 text-accent px-1${
          className ? ` ${className}` : ''
        }`}
      >
        NEW
      </span>
    );
  }

  const value = delta ?? 0;
  const isUp = value > 0.005;
  const isDown = value < -0.005;
  const glyph = isUp ? '▲' : isDown ? '▼' : '■';
  const tone = isUp ? 'text-up' : isDown ? 'text-down' : 'text-ink-mute';
  const sign = isUp ? '+' : '';
  const label = `${glyph}${sign}${value.toFixed(decimals)}`;

  return (
    <span
      className={`tabular-nums text-[10px] font-mono ${tone}${className ? ` ${className}` : ''}`}
    >
      {label}
    </span>
  );
}
