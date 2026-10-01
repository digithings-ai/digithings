/**
 * Pure model for the desk-view heat grid: brokers x the 8 board currencies,
 * each cell a signed conviction weight (+ bullish, - bearish, 0 watch/neutral,
 * null no view), plus the marginals — crowd net lean per currency (bottom) and
 * view count per desk (right).
 */
import { MATRIX_COLUMNS } from './types';
import type { MatrixCell } from './types';
import { directionBucket } from './matrix-format';

export interface ColumnCrowd {
  column: string;
  bull: number;
  bear: number;
  watch: number;
  neutral: number;
  total: number;
  /** (bull - bear) / total in [-1, 1]; null with no views. */
  net: number | null;
}

export interface MatrixHeat {
  brokers: string[];
  columns: readonly string[];
  /** values[broker][column] */
  values: Array<Array<number | null>>;
  crowd: ColumnCrowd[];
  /** Number of columns each broker has a view on. */
  activity: number[];
}

/** Conviction word to a 0..1 weight; unknown words sit mid-scale. */
export function convictionWeight(conviction: string): number {
  const c = conviction.trim().toLowerCase();
  if (c === 'high') return 1;
  if (c === 'medium' || c === 'mid') return 0.66;
  if (c === 'low') return 0.33;
  return 0.5;
}

export function cellValue(cell: Pick<MatrixCell, 'direction' | 'conviction'>): number {
  const bucket = directionBucket(cell.direction);
  const w = convictionWeight(cell.conviction);
  if (bucket === 'bull') return w;
  if (bucket === 'bear') return -w;
  return 0;
}

export function deriveMatrixHeat(cells: MatrixCell[]): MatrixHeat {
  const brokers = [...new Set(cells.map((c) => c.broker))].sort((a, b) => a.localeCompare(b));
  const byKey = new Map<string, MatrixCell>();
  for (const c of cells) byKey.set(`${c.broker}|${c.column}`, c);

  const values = brokers.map((b) =>
    MATRIX_COLUMNS.map((col) => {
      const cell = byKey.get(`${b}|${col}`);
      return cell ? cellValue(cell) : null;
    }),
  );

  const crowd: ColumnCrowd[] = MATRIX_COLUMNS.map((column) => {
    const tally = { bull: 0, bear: 0, watch: 0, neutral: 0 };
    for (const b of brokers) {
      const cell = byKey.get(`${b}|${column}`);
      if (cell) tally[directionBucket(cell.direction)] += 1;
    }
    const total = tally.bull + tally.bear + tally.watch + tally.neutral;
    return { column, ...tally, total, net: total > 0 ? (tally.bull - tally.bear) / total : null };
  });

  const activity = values.map((row) => row.filter((v) => v !== null).length);
  return { brokers, columns: MATRIX_COLUMNS, values, crowd, activity };
}

/** Text alternative for the heat grid. */
export function matrixHeatSummary(heat: MatrixHeat): string {
  if (heat.brokers.length === 0) return 'Desk view heat grid: no desk views.';
  const lean = heat.crowd
    .filter((c) => c.total > 0)
    .map((c) => `${c.column} ${c.bull} bullish ${c.bear} bearish of ${c.total}`)
    .join('; ');
  return `Desk view heat grid, ${heat.brokers.length} desks by ${heat.columns.length} currencies. Crowd lean: ${lean}.`;
}
