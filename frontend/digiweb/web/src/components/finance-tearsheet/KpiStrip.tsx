/**
 * KpiStrip + Kpi (#1463) — the tearsheet KPI card grammar promoted from the
 * inline `Kpi` in frontend/digiquant-web/components/tearsheet/tearsheet-view.tsx
 * and olympus' OlympusTearsheetView. Values are ReactNodes so consumers tone
 * them with the money classes (`is-pos` / `is-neg` via `toneClass`); the
 * gradient card surface, the 6-up `primary` strip (3-up ≤1100px, 2-up
 * ≤640px), and the `break-inside: avoid` print rules live in
 * styles/finance-tearsheet.css. Server component — no state, no effects.
 */
import type { ReactNode } from "react";

export interface KpiProps {
  label: string;
  value: ReactNode;
  /** Small soft line under the value (e.g. "since inception"). */
  sub?: ReactNode;
}

export function Kpi({ label, value, sub }: KpiProps) {
  return (
    <div className="ts-kpi">
      <span className="ts-kpi-label">{label}</span>
      <span className="ts-kpi-value">{value}</span>
      {sub != null ? <span className="ts-kpi-sub">{sub}</span> : null}
    </div>
  );
}

export interface KpiStripProps {
  children: ReactNode;
  /** The headline 6-up strip (`.ts-kpis-primary`); omit for the auto-fit grid. */
  primary?: boolean;
  /** Names the strip for AT (e.g. "Headline performance"). */
  ariaLabel?: string;
  className?: string;
}

export function KpiStrip({ children, primary = false, ariaLabel, className }: KpiStripProps) {
  return (
    <section
      className={
        "ts-kpis" + (primary ? " ts-kpis-primary" : "") + (className ? ` ${className}` : "")
      }
      aria-label={ariaLabel}
    >
      {children}
    </section>
  );
}
