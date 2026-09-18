'use client';

import type { ReactNode } from 'react';
import { Card } from '@digithings/web/ui';

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
  flat = false,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  color?: string;
  flat?: boolean;
}) {
  return (
    <Card
      data-reveal={flat ? undefined : true}
      className={`gap-0 flex flex-col gap-1 p-4 ${
        flat ? 'border-b border-r border-hair bg-transparent ring-0' : ''
      }`}
    >
      <span className="text-xs text-ink-mute">{label}</span>
      <span className={`text-xl font-semibold tabular-nums ${color ?? 'text-ink'}`}>
        {value}
      </span>
      {sub ? <span className="text-xs text-ink-mute">{sub}</span> : null}
    </Card>
  );
}

export function SectionCard({
  title,
  subtitle,
  children,
  className,
  flat = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  flat?: boolean;
}) {
  return (
    <Card
      data-reveal={flat ? undefined : true}
      className={`gap-0 flex flex-col gap-4 ${
        flat ? 'border-b border-hair bg-transparent py-5 ring-0' : 'p-5'
      } ${className ?? ''}`}
    >
      <div className="flex flex-col gap-0.5">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {subtitle ? <p className="text-xs text-ink-mute">{subtitle}</p> : null}
      </div>
      {children}
    </Card>
  );
}

