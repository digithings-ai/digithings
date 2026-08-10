/**
 * PerfMetrics — the tearsheet grade block promoted from the design reference
 * (finance/perf-metrics): labels in mono micro-caps, values in large tabular
 * numerals, laid out on an n-up hairline grid. Only reads that carry money
 * meaning take `tone: "up" | "down"` (--up / --down phosphor semantics);
 * everything else stays ink so the eye goes to what matters.
 *
 * The hairline cell grid is sibling-index CSS (styles/metrics.css) keyed off
 * the container's `data-cols` — Tailwind can't express nth-child, so that
 * grammar stays CSS. Below 720px the grid collapses to two-up and the
 * borders re-derive. Server component — no state, no effects.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/metrics.css";
 *                 @source "<path-to>/digiweb/web/src/components/metrics";
 */
export type PerfMetric = {
  /** Mono micro-caps label — "CAGR", "Sharpe", "Max drawdown" … */
  label: string;
  /** Preformatted display value — "+44.9%", "1.82" … */
  value: string;
  /** Optional muted unit suffix rendered after the value — "%", "bps", "×". */
  unit?: string;
  /** Money semantics: only return / drawdown-class reads take a tone. */
  tone?: "up" | "down";
};

const COLS: Record<2 | 3 | 4, string> = {
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
};

export function PerfMetrics({
  metrics,
  columns = 4,
  className,
}: {
  metrics: PerfMetric[];
  /** Desktop cells per row (collapses to 2 below 720px). */
  columns?: 2 | 3 | 4;
  className?: string;
}) {
  return (
    <div
      data-cols={columns}
      className={`perf-metrics grid ${COLS[columns]} overflow-hidden rounded-[12px] border border-hair bg-surface max-[720px]:grid-cols-2${
        className ? ` ${className}` : ""
      }`}
    >
      {metrics.map((m) => (
        <div key={m.label} className="perf-metric p-[1.2rem]">
          <span className="block font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
            {m.label}
          </span>
          <span
            className={`mt-[0.35rem] block font-mono text-[1.5rem] [font-variant-numeric:tabular-nums] ${
              m.tone === "up" ? "text-up" : m.tone === "down" ? "text-down" : "text-ink"
            }`}
          >
            {m.value}
            {m.unit ? <span className="ml-[0.15em] text-[0.85rem] text-ink-mute">{m.unit}</span> : null}
          </span>
        </div>
      ))}
    </div>
  );
}
