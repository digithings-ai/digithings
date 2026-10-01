import type { Layout } from './grid';

const L = (rows: [string, number, number, number, number][]): Layout => rows.map(([id, x, y, w, h]) => ({ id, x, y, w, h }));

/**
 * Default block layouts, by page path. Which blocks a caller may actually use is
 * decided by the access manifest (locked blocks render as locked); a layout may
 * therefore name blocks the caller cannot open.
 */
export const PAGE_LAYOUTS: Record<string, Layout> = {
  '/brief': L([['brief', 1, 1, 8, 3], ['live', 9, 1, 4, 3], ['decision', 1, 4, 6, 3], ['risks', 7, 4, 6, 3], ['performance', 1, 7, 12, 6]]),
  '/portfolio': L([['portfolio', 1, 1, 4, 6], ['sleeves', 5, 1, 4, 6], ['movers', 9, 1, 4, 6], ['book', 1, 7, 6, 6], ['nav', 7, 7, 3, 6], ['drawdown', 10, 7, 3, 6]]),
  '/portfolio/holdings': L([['holdings', 1, 1, 12, 12]]),
  '/portfolio/attribution': L([['attribution', 1, 1, 12, 12]]),
  '/portfolio/ledger': L([['ledger', 1, 1, 8, 12], ['cash', 9, 1, 4, 12]]),
  '/portfolio/tearsheet': L([['performance', 1, 1, 6, 6], ['navtable', 7, 1, 6, 6], ['benchmarks', 1, 7, 6, 6], ['drawdown', 7, 7, 6, 6]]),
  '/portfolio/theses': L([['theses', 1, 1, 8, 12], ['signals', 9, 1, 4, 12]]),
  '/pipeline': L([['pl-run-health', 1, 1, 4, 4], ['pl-narrative', 5, 1, 4, 4], ['pl-artifacts', 9, 1, 4, 4], ['pl-canvas', 1, 5, 8, 8], ['pl-node-document', 9, 5, 4, 4], ['pl-call-trace', 9, 9, 4, 4]]),
};
