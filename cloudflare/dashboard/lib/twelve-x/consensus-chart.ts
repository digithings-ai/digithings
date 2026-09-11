/**
 * Pure chart transformation helpers for the Consensus chart surface.
 *
 * Handles stale-series extension: when a currency's last finite observation
 * precedes the global latest run_date, emit a `CCY__stale` series anchored at
 * the last known point and held constant to the latest chart date. The stale
 * extension renders as a dotted/dashed line, signaling missing recent data
 * without fabricating scores.
 */

/** One pivoted score row: one entry per run_date, one numeric key per currency. */
export interface ScoreSeriesRow {
  run_date: string;
  [currency: string]: number | string | null;
}

/**
 * Augment a score time series with stale-currency extensions.
 *
 * For each currency in `currencies`, finds its last finite observation. If that
 * date precedes the global latest run_date in the chart, emits a parallel
 * `{currency}__stale` series holding the last known value from the anchor date
 * to the latest chart date. The observed series remains unchanged (null gaps
 * preserved). Does not extend beyond the latest real chart date or fabricate
 * new rows.
 *
 * @param chartData One row per run_date, with currency keys holding scores
 * @param currencies The set of currencies present in the chart
 * @returns The same rows, augmented with `{currency}__stale` keys where needed
 */
export function augmentWithStaleSeries(
  chartData: ScoreSeriesRow[],
  currencies: string[],
): ScoreSeriesRow[] {
  if (chartData.length === 0) return [];

  // Find the global latest run_date in the chart
  const latestDate = chartData[chartData.length - 1].run_date;

  // For each currency, find its last finite observation date
  const lastFiniteDate = new Map<string, string>();
  const lastFiniteValue = new Map<string, number>();

  for (const ccy of currencies) {
    for (let i = chartData.length - 1; i >= 0; i--) {
      const val = chartData[i][ccy];
      if (typeof val === 'number' && Number.isFinite(val)) {
        lastFiniteDate.set(ccy, chartData[i].run_date);
        lastFiniteValue.set(ccy, val);
        break;
      }
    }
  }

  // Clone the chart data and augment with stale series
  return chartData.map((row) => {
    const augmented = { ...row };
    for (const ccy of currencies) {
      const lastDate = lastFiniteDate.get(ccy);
      const lastValue = lastFiniteValue.get(ccy);

      // Include the last real point so the dashed segment connects to the
      // observed series, then carry it only across existing later rows.
      if (lastDate && lastValue !== undefined && lastDate < latestDate && row.run_date >= lastDate) {
        augmented[`${ccy}__stale`] = lastValue;
      }
    }
    return augmented;
  });
}
