import { ReactNode, ElementType } from 'react';

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ElementType<{ size?: number; className?: string }>;
  iconColor?: string;
  subtitle?: ReactNode;
  valueClass?: string;
}

interface BadgeProps {
  children: ReactNode;
  variant?: 'default' | 'blue' | 'green' | 'red' | 'amber';
  className?: string;
}

interface SectionTitleProps {
  children: ReactNode;
  className?: string;
}

/** Reusable stat card for KPI display */
export function StatCard({
  label,
  value,
  icon: Icon,
  iconColor = 'text-accent',
  subtitle,
  valueClass = '',
}: StatCardProps) {
  return (
    <div className="glass-card p-6">
      <div className="flex justify-between items-start">
        <span className="text-xs font-semibold uppercase tracking-widest text-ink-mute">{label}</span>
        {Icon && <Icon size={16} className={iconColor} />}
      </div>
      <div className={`text-3xl font-bold tabular-nums mt-2 ${valueClass}`}>
        {value}
      </div>
      {subtitle && (
        <p className="text-xs text-ink-mute mt-2">{subtitle}</p>
      )}
    </div>
  );
}

/** Badge variant */
export function Badge({ children, variant = 'default', className = '' }: BadgeProps) {
  const variants: Record<NonNullable<BadgeProps['variant']>, string> = {
    default: 'bg-ink/10 text-ink-soft border-hair',
    blue: 'bg-accent/15 text-accent border-accent/30',
    green: 'bg-up/15 text-up border-up/30',
    red: 'bg-down/15 text-down border-down/30',
    amber: 'bg-warn/15 text-warn border-warn/30',
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold tracking-wide border ${variants[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Section heading used inside pages */
export function SectionTitle({ children, className = '' }: SectionTitleProps) {
  return (
    <h3 className={`text-lg font-semibold mb-3 ${className}`}>{children}</h3>
  );
}

/** Format percentage with sign */
export function formatPct(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
}

/** Return Tailwind color class for positive/negative */
export function pnlColor(v: number | null | undefined): string {
  if (v == null) return '';
  return v >= 0 ? 'text-up' : 'text-down';
}
