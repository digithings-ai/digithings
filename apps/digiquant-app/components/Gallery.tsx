'use client';

import { BlockGrid } from './BlockGrid';
import { GROUP_PAGES } from '@/lib/group-pages';
import type { Layout, Placement } from '@/lib/grid';

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

/** Auto-tile up to 9 blocks: 2×2 of 6×6 for ≤4, else 3×3 of 4×4. The rest are one `+ id` away in edit mode. */
function tile(ids: string[]): Layout {
  const shown = ids.slice(0, 9);
  const per = shown.length <= 4 ? 2 : 3;
  const w = 12 / per, h = Math.floor(12 / Math.ceil(shown.length / per));
  return shown.map((id, i): Placement => ({ id, x: (i % per) * w + 1, y: Math.floor(i / per) * h + 1, w, h }));
}


/** Dev page: one block group on the editable grid. */
export function GroupGallery({ group }: { group: string }) {
  const ids = GROUP_PAGES[group] ?? [];
  return <BlockGrid pageId={`blocks-${group}`} initial={tile(ids)} />;
}
