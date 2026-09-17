import { ReactNode, ElementType, type ComponentProps } from 'react';
import { Badge as KitBadge, Card } from '@digithings/web/ui';

/** The kit Badge's own prop surface, derived locally (the kit does not export
 *  its prop type). Includes the `variant` axis from `badgeVariants`. */
type KitBadgeProps = ComponentProps<typeof KitBadge>;

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ElementType<{ size?: number; className?: string }>;
  iconColor?: string;
  subtitle?: ReactNode;
  valueClass?: string;
}

/** dashboard's historical tone names, kept so call sites need zero churn. */
type DashboardBadgeVariant = 'default' | 'blue' | 'green' | 'red' | 'amber';

type BadgeProps = Omit<KitBadgeProps, 'variant'> & {
  variant?: DashboardBadgeVariant;
};

interface SectionTitleProps {
  children: ReactNode;
  className?: string;
}

/** Reusable stat card for KPI display.
 *
 * Wave-2 (#4206): the box is now the kit `Card` (same `--surface` fill, zero
 * radius, hairline ring) and the scroll-reveal hook is the `data-reveal`
 * attribute — MotionLayer no longer needs the retired `.oly-slab` class. */
export function StatCard({
  label,
  value,
  icon: Icon,
  iconColor = 'text-accent',
  subtitle,
  valueClass = '',
}: StatCardProps) {
  return (
    <Card data-reveal className="min-h-36 gap-0 px-5 py-5">
      <div className="flex items-start justify-between gap-3">
        <span className="font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
          {label}
        </span>
        {Icon && <Icon size={15} className={iconColor} aria-hidden="true" />}
      </div>
      <div
        className={`mt-3 font-mono text-[clamp(1.55rem,3vw,2.1rem)] font-normal leading-none tabular-nums text-ink ${valueClass}`}
      >
        {value}
      </div>
      {subtitle && (
        <p className="mt-auto pt-3 font-mono text-[0.66rem] leading-relaxed text-ink-mute">
          {subtitle}
        </p>
      )}
    </Card>
  );
}

/** dashboard tone → kit Badge tone utilities (same color semantics). */
const BADGE_TONE: Record<DashboardBadgeVariant, string> = {
  default: 'text-ink-mute',
  blue: 'border-accent-weak text-accent',
  green: 'border-up/40 text-up',
  red: 'border-down/40 text-down',
  amber: 'border-warn/40 text-warn',
};

/** Badge — thin tone mapper over the vendored kit `Badge` (@digithings/web/ui).
 *
 * Decision (#4206): the old reference-dress shim (controls-layer Badge
 * `dress="reference"`) is deleted; dashboard's historical tone names map onto
 * the kit outline badge plus token utilities, so every call site keeps its
 * color semantics with zero churn. Extra props (data-testid, aria-*) pass
 * through to the rendered span. */
export function Badge({ variant = 'default', className = '', ...props }: BadgeProps) {
  return (
    <KitBadge
      variant="outline"
      className={`${BADGE_TONE[variant]} ${className}`.trim()}
      {...props}
    />
  );
}

/** Section heading used inside pages */
export function SectionTitle({ children, className = '' }: SectionTitleProps) {
  return (
    <h3 className={`mb-3 font-display text-xl font-normal tracking-tight text-ink ${className}`}>
      {children}
    </h3>
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
