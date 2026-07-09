/**
 * MonthlyReturns — the tearsheet heatmap promoted from the design reference
 * (finance/monthly-returns): months across, years down, each cell tinted by
 * its return — deeper `--up` for stronger gains, `--down` for losses, empty
 * where there is no data yet — with the year column carrying the YTD total in
 * the money colors. Categorical surface, not time-series, so it stays a real
 * `<table>` (readable with no JS, no chart engine; see the lightweight-charts
 * ruling in frontend/olympus/lib/CHARTS.md).
 *
 * The tint magnitude is a computed inline `color-mix()` on the money tokens.
 * The table grammar lives in styles/finance-charts.css per migrate-vs-leave:
 * the td tint interacts with the per-cell inline styles, and the YTD money
 * colors need the `.mr-table td.mr-ytd.up/.down` descendant specificity to
 * beat the base td color. Server component — no state, no effects.
 *
 * Data comes in via the required `rows` prop; `MONTHLY_RETURNS_DEMO` is the
 * exported reference filler. Wiring (consuming app):
 *   globals.css   @import "@digithings/web/styles/finance-charts.css";
 *                 @source "<path-to>/digiweb/web/src/components/finance-charts";
 */

const DEFAULT_MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

export type MonthlyReturnRow = {
  /** Row header — the year (or any period label). */
  year: number | string;
  /** Per-month % returns aligned to `monthLabels`; `null` = no data yet. */
  values: (number | null)[];
  /** Period total (%); summed from `values` (1 dp) when omitted. */
  ytd?: number;
};

export type MonthlyReturnsProps = {
  /** Heatmap rows, one per year. */
  rows: MonthlyReturnRow[];
  /** Column headers; defaults to Jan–Dec. */
  monthLabels?: string[];
  /** |return| (%) mapped to the deepest cell tint. */
  peak?: number;
  /** Header on the totals column. */
  ytdLabel?: string;
  /** Extra classes on the scroll wrapper. */
  className?: string;
};

/** Cell tint: mix the money token toward transparent by |return| / peak;
 *  past half depth the ink flips to `--bg` so the figure stays readable. */
function cellStyle(value: number | null, peak: number) {
  if (value === null) return undefined;
  const mag = Math.min(1, Math.abs(value) / peak);
  const token = value >= 0 ? "--up" : "--down";
  return {
    background: `color-mix(in srgb, var(${token}) ${Math.round(mag * 72)}%, transparent)`,
    color: mag > 0.5 ? "var(--bg)" : "var(--ink)",
  } as const;
}

export function MonthlyReturns({
  rows,
  monthLabels = DEFAULT_MONTHS,
  peak = 18,
  ytdLabel = "Year",
  className,
}: MonthlyReturnsProps) {
  return (
    <div className={`overflow-x-auto${className ? ` ${className}` : ""}`}>
      <table className="mr-table">
        <thead>
          <tr>
            <th scope="col" aria-label="Period" />
            {monthLabels.map((mo) => (
              <th key={mo} scope="col">
                {mo}
              </th>
            ))}
            <th scope="col" className="mr-ytd-head">
              {ytdLabel}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const ytd =
              row.ytd ??
              Math.round(row.values.reduce<number>((a, v) => a + (v ?? 0), 0) * 10) / 10;
            return (
              <tr key={row.year}>
                <th scope="row">{row.year}</th>
                {row.values.map((v, i) => (
                  <td key={i} style={cellStyle(v, peak)}>
                    {v === null ? "" : v.toFixed(1)}
                  </td>
                ))}
                <td className={`mr-ytd ${ytd >= 0 ? "up" : "down"}`}>
                  {ytd >= 0 ? "+" : ""}
                  {ytd.toFixed(1)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
