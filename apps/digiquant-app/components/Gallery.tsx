'use client';

import { BlockGrid } from './BlockGrid';
import type { Layout } from '@/lib/grid';

const DEFAULT: Layout = [
  { id: 'book', x: 1, y: 1, w: 4, h: 6 },
  { id: 'portfolio', x: 5, y: 1, w: 4, h: 6 },
  { id: 'brief', x: 9, y: 1, w: 4, h: 3 },
  { id: 'live', x: 9, y: 4, w: 4, h: 3 },
  { id: 'performance', x: 1, y: 7, w: 4, h: 6 },
  { id: 'nav', x: 5, y: 7, w: 4, h: 6 },
  { id: 'benchmarks', x: 9, y: 7, w: 4, h: 3 },
  { id: 'ledger', x: 9, y: 10, w: 4, h: 3 },
];

const PORTFOLIO: Layout = [
  { id: 'holdings', x: 1, y: 1, w: 8, h: 6 },
  { id: 'sleeves', x: 9, y: 1, w: 4, h: 3 },
  { id: 'movers', x: 9, y: 4, w: 4, h: 3 },
  { id: 'decision', x: 1, y: 7, w: 4, h: 3 },
  { id: 'risks', x: 5, y: 7, w: 4, h: 3 },
  { id: 'drawdown', x: 9, y: 7, w: 4, h: 3 },
  { id: 'theses', x: 1, y: 10, w: 6, h: 3 },
  { id: 'signals', x: 7, y: 10, w: 3, h: 3 },
  { id: 'attribution', x: 10, y: 10, w: 3, h: 3 },
];

/** Dev page: every registered block on the editable grid. */
export function Gallery() {
  return <BlockGrid pageId="blocks" initial={DEFAULT} />;
}

/** Dev page: the portfolio group on the editable grid. */
export function PortfolioGallery() {
  return <BlockGrid pageId="blocks-portfolio" initial={PORTFOLIO} />;
}
