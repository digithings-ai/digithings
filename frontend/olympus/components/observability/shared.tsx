'use client';

import type { ReactNode } from 'react';

/** Percent points → "+3.20%" / "-1.50%" / "—" for null. */
export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—';
  const s = v.toFixed(digits);
  return `${v > 0 ? '+' : ''}${s}%`;
}

export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || Number.isNaN(v)) return '—';
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Green for gains, red for losses, muted for flat/missing — the fin-* convention. */
export function signColorClass(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v) || v === 0) return 'text-ink-soft';
  return v > 0 ? 'text-up' : 'text-down';
}

export function StatTile({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  color?: string;
}) {
  return (
    <div className="glass-card p-4 flex flex-col gap-1">
      <span className="text-xs text-ink-mute">{label}</span>
      <span className={`text-xl font-semibold tabular-nums ${color ?? 'text-ink'}`}>
        {value}
      </span>
      {sub ? <span className="text-xs text-ink-mute">{sub}</span> : null}
    </div>
  );
}

export function SectionCard({
  title,
  subtitle,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`glass-card p-5 flex flex-col gap-4 ${className ?? ''}`}>
      <div className="flex flex-col gap-0.5">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {subtitle ? <p className="text-xs text-ink-mute">{subtitle}</p> : null}
      </div>
      {children}
    </div>
  );
}

export function EmptyState({
  title,
  message,
  note,
}: {
  title: string;
  message: string;
  /** Short secondary line for PMs — explains why the tab is empty without reading as "broken". */
  note?: string;
}) {
  return (
    <div className="glass-card p-8 flex flex-col items-center justify-center gap-2 text-center">
      <p className="text-sm font-medium text-ink-soft">{title}</p>
      <p className="text-xs text-ink-mute max-w-md">{message}</p>
      {note ? (
        <p className="text-xs text-ink-mute/60 max-w-md mt-1 italic">{note}</p>
      ) : null}
    </div>
  );
}
