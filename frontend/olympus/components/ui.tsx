import { ReactNode, ElementType } from 'react';
import {
  Badge as ControlBadge,
  type BadgeProps as ControlBadgeProps,
  type BadgeReferenceVariant,
} from '@digithings/web';

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ElementType<{ size?: number; className?: string }>;
  iconColor?: string;
  subtitle?: ReactNode;
  valueClass?: string;
}

/** Olympus's historical tone names, kept so call sites need zero churn. */
type OlympusBadgeVariant = 'default' | 'blue' | 'green' | 'red' | 'amber';

type BadgeProps = Omit<
  Extract<ControlBadgeProps, { dress?: 'reference' }>,
  'dress' | 'variant'
> & {
  variant?: OlympusBadgeVariant;
};

interface SectionTitleProps {
  children: ReactNode;
  className?: string;
}

/** Reusable stat card for KPI display.
 *
 * F4 ruling (#1450): stays LOCAL — the promoted controls Card (ctl-card-ref:
 * 12px radius, ruled header rows, no shadow/hover) and the metrics grammar
 * (PerfMetrics: n-up hairline grid, mono values) both render a different
 * look, and the `.glass-card` class here is load-bearing for MotionLayer's
 * scroll-reveal system (globals.css `html.motion-on .glass-card`). */
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

/** Olympus tone → shared reference-dress tone (same color semantics). */
const BADGE_TONE: Record<OlympusBadgeVariant, BadgeReferenceVariant> = {
  default: 'neutral',
  blue: 'accent',
  green: 'up',
  red: 'down',
  amber: 'warn',
};

/** Badge — thin re-export of the shared @digithings/web controls Badge
 * (#1419 shim pattern, adopted for F4 #1450). Pinned to dress="reference"
 * (the .dg-tier mono micro-caps hairline pill); olympus's historical tone
 * names map onto the shared tones so every call site keeps its color
 * semantics with zero churn. Extra props (data-testid, aria-*) now pass
 * through to the rendered span. */
export function Badge({ variant = 'default', ...props }: BadgeProps) {
  return <ControlBadge dress="reference" variant={BADGE_TONE[variant]} {...props} />;
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
