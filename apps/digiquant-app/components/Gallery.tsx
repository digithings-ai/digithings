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

/** Dev page: every registered block on the editable grid. */
export function Gallery() {
  return <BlockGrid pageId="blocks" initial={DEFAULT} />;
}
