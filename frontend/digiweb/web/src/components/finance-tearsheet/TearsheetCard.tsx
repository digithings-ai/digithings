/**
 * TearsheetCard (#1463) — the strategy-library card dress promoted from
 * frontend/digiquant-web/components/tearsheet/strategy-card.tsx, closing the
 * gap recorded against the promoted controls Card (anchor/render composition
 * plus a tearsheet dress): the whole card is a link, with hover-lift +
 * accent-border transition over the gradient surface (`.ts-card` in
 * styles/finance-tearsheet.css; `break-inside: avoid` in print). Head/title
 * markup stays consumer-composed on the shared classes (`.ts-card-head`,
 * `.ts-card-title`, `.ts-card-name` …); the KPI grid grammar ships as
 * TearsheetCardKpis / TearsheetCardKpi. Server components — no state.
 */
import type { AnchorHTMLAttributes, ReactNode } from "react";

export interface TearsheetCardProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  /** Renders an anchor when set; a plain div card otherwise. */
  href?: string;
  children: ReactNode;
}

export function TearsheetCard({ href, className, children, ...rest }: TearsheetCardProps) {
  const cls = "ts-card" + (className ? ` ${className}` : "");
  if (href) {
    return (
      <a className={cls} href={href} {...rest}>
        {children}
      </a>
    );
  }
  return <div className={cls}>{children}</div>;
}

/** The 2-column KPI grid inside a card (`.ts-card-kpis`). */
export function TearsheetCardKpis({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={"ts-card-kpis" + (className ? ` ${className}` : "")}>{children}</div>
  );
}

/** One label-over-value cell in the card KPI grid. Values are ReactNodes so
 *  consumers tone them with the money classes (`toneClass`). */
export function TearsheetCardKpi({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="ts-card-kpi">
      <span className="ts-card-kpi-label">{label}</span>
      <span className="ts-card-kpi-value">{value}</span>
    </div>
  );
}
