/**
 * Holdings column priority. Narrow panes drop provenance and long text
 * first. Identity and the number that matters stay: Ticker, Weight, Day, Mark.
 */

export const HOLDINGS_KEEP_COLUMNS = ['Ticker', 'Weight', 'Day', 'Mark'] as const;

/** Drop order as the pane gets narrower: first name leaves first. */
export const HOLDINGS_DROP_ORDER = ['Source', 'Thesis', 'Shares', 'Value', 'Name'] as const;

export type HoldingsDropColumn = (typeof HOLDINGS_DROP_ORDER)[number];

/**
 * Minimum pane width (px) that still shows the column.
 * Below it, that column is hidden. Keep-columns have no floor.
 */
export const HOLDINGS_MIN_WIDTH: Record<HoldingsDropColumn, number> = {
  Source: 940,
  Thesis: 800,
  Shares: 660,
  Value: 540,
  Name: 420,
};

/** Display order for a full holdings table. */
export const HOLDINGS_COLUMN_ORDER = [
  'Ticker',
  'Name',
  'Weight',
  'Day',
  'Mark',
  'Value',
  'Shares',
  'Thesis',
  'Source',
] as const;

export function visibleHoldingsColumns(
  widthPx: number,
  columnIds: readonly string[] = HOLDINGS_COLUMN_ORDER,
): string[] {
  const hidden = new Set<string>();
  for (const column of HOLDINGS_DROP_ORDER) {
    if (widthPx < HOLDINGS_MIN_WIDTH[column]) hidden.add(column);
  }
  return columnIds.filter((id) => !hidden.has(id));
}
