import type { ReactNode } from "react";

/**
 * PerformanceDashboard — the book-level surface promoted from the design
 * reference (finance/performance-dashboard): a value/return headline row, a
 * strip of aggregate ratios, and an allocation-by-strategy breakdown. Sits
 * above the single-strategy tearsheet metrics (<PerfMetrics/>): this is the
 * whole book. P&L reads wear the money colors (`tone`); ratios stay ink; the
 * allocation bars take the module accent. Server component — no state, no
 * effects.
 *
 * `children` is the composite slot: an optional chart section rendered
 * between the headline row and the ratio strip (intended for the
 * finance-charts family — <EquityCurve/>, <SyncedTearsheet/> — passed in by
 * the page, never imported here). Give the slot content a definite height;
 * the dashboard only contributes the hairline divider.
 *
 * The hairline grammar between headline cells and ratio cells is
 * sibling-index CSS (styles/finance-composites.css, pdash-*) keyed off the
 * strip's `data-cols` — Tailwind can't express nth-child, so it stays CSS.
 * Below 720px the headline stacks and the ratio strip collapses to 3-up.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/finance-composites.css";
 *                 @source "<path-to>/digiweb/web/src/components/finance-composites";
 */
export type DashboardHeadline = {
  /** Mono micro-caps label — "portfolio value", "total return" … */
  label: string;
  /** Big tabular read — "$1.284M", "+28.4%" … */
  value: string;
  /** Money semantics on the value: only P&L reads take a tone. */
  tone?: "up" | "down";
  /** Small line under the value — "+$5.47K · +0.43% today", "since inception · 2y" … */
  note?: string;
  /** Money semantics on the note; untoned notes read muted ink. */
  noteTone?: "up" | "down";
};

export type DashboardRatio = {
  /** Mono micro-caps label — "sharpe", "max drawdown" … */
  label: string;
  /** Preformatted read — "2.31", "−18.4%" … */
  value: string;
  /** Money semantics: drawdown-class reads take "down"; ratios stay ink. */
  tone?: "up" | "down";
};

export type DashboardAllocation = {
  /** Strategy / sleeve name — "trend_xsec" … */
  name: string;
  /** Share of the book, 0–100; drives the accent bar width. */
  pct: number;
};

export type PerformanceDashboardProps = {
  /** Headline cells; designed for two (value + return), 1.4fr/1fr split. */
  headlines: DashboardHeadline[];
  ratios?: DashboardRatio[];
  /** Desktop ratio cells per row (collapses to 3-up below 720px). */
  ratioColumns?: 3 | 4 | 5 | 6;
  allocations?: DashboardAllocation[];
  /** Mono micro-caps heading over the allocation bars. */
  allocationsLabel?: string;
  /** Optional chart slot rendered after the headline row (see docblock). */
  children?: ReactNode;
  /** Extra classes on the dashboard shell (margins — the call site's business). */
  className?: string;
};

const HEAD_COLS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-[1.4fr_1fr]",
  3: "grid-cols-3",
  4: "grid-cols-4",
};

const RATIO_COLS: Record<3 | 4 | 5 | 6, string> = {
  3: "grid-cols-3",
  4: "grid-cols-4",
  5: "grid-cols-5",
  6: "grid-cols-6",
};

export function PerformanceDashboard({
  headlines,
  ratios,
  ratioColumns = 6,
  allocations,
  allocationsLabel = "allocation by strategy",
  children,
  className,
}: PerformanceDashboardProps) {
  return (
    <div
      className={`overflow-hidden rounded-[12px] border border-hair bg-surface${
        className ? ` ${className}` : ""
      }`}
    >
      <div className={`grid ${HEAD_COLS[headlines.length] ?? "grid-cols-2"} max-[720px]:grid-cols-1`}>
        {headlines.map((h) => (
          <div
            key={h.label}
            className="pdash-head flex flex-col gap-[0.3rem] px-[1.4rem] pb-[1.2rem] pt-[1.4rem]"
          >
            <span className="font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
              {h.label}
            </span>
            <span
              className={`font-mono text-[clamp(1.6rem,4vw,2.2rem)] [font-variant-numeric:tabular-nums] ${
                h.tone === "up" ? "text-up" : h.tone === "down" ? "text-down" : "text-ink"
              }`}
            >
              {h.value}
            </span>
            {h.note ? (
              <span
                className={`font-mono ${
                  h.noteTone === "up"
                    ? "text-[0.72rem] text-up"
                    : h.noteTone === "down"
                      ? "text-[0.72rem] text-down"
                      : "text-[0.66rem] text-ink-mute"
                }`}
              >
                {h.note}
              </span>
            ) : null}
          </div>
        ))}
      </div>

      {children ? <div className="border-t border-hair">{children}</div> : null}

      {ratios && ratios.length > 0 ? (
        <div
          data-cols={ratioColumns}
          className={`pdash-ratios grid ${RATIO_COLS[ratioColumns]} border-t border-hair max-[720px]:grid-cols-3`}
        >
          {ratios.map((r) => (
            <div key={r.label} className="pdash-ratio flex flex-col gap-[0.3rem] px-4 py-[0.9rem]">
              <span className="font-mono text-[0.52rem] uppercase tracking-[0.08em] text-ink-mute">
                {r.label}
              </span>
              <span
                className={`font-mono text-[0.98rem] [font-variant-numeric:tabular-nums] ${
                  r.tone === "up" ? "text-up" : r.tone === "down" ? "text-down" : "text-ink"
                }`}
              >
                {r.value}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {allocations && allocations.length > 0 ? (
        <div className="border-t border-hair px-[1.4rem] pb-[1.4rem] pt-[1.2rem]">
          <p className="mx-0 mb-[0.8rem] mt-0 font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            {allocationsLabel}
          </p>
          {allocations.map((a) => (
            <div
              key={a.name}
              className="grid grid-cols-[6rem_1fr_3rem] items-center gap-[0.9rem] py-[0.35rem] font-mono text-[0.78rem] text-ink-soft"
            >
              <span className="text-ink">{a.name}</span>
              <span className="h-2 overflow-hidden rounded-full bg-ink/[0.08]">
                <span
                  className="block h-full rounded-full bg-accent"
                  style={{ width: `${a.pct}%` }}
                />
              </span>
              <span className="text-right text-ink-soft [font-variant-numeric:tabular-nums]">
                {a.pct}%
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
