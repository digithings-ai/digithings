/**
 * TODO(slice-a): `DeskPaneModel` moves to the shell `PaneFrame` module.
 * Brief defines the same shape so panes can mount before the shell lands.
 */
import type { PaneState } from '@/components/desk/atoms/DeskState';

export type { PaneState };

export type DeskPaneModel = {
  id: string;
  title: string;
  chromePath: string;
  eyebrow: string;
  state: PaneState;
  errorMessage?: string;
  columns?: number;
};

/** Static identity. Runtime state is applied in `buildBriefPanes`. */
export const BRIEF_PANES: readonly DeskPaneModel[] = [
  {
    id: 'decision',
    title: 'Decision',
    eyebrow: '01',
    chromePath: '/house/brief',
    columns: 5,
    state: 'loading',
  },
  {
    id: 'signals',
    title: 'Signals to resolve',
    eyebrow: '02',
    chromePath: '/house/brief/signals',
    columns: 7,
    state: 'loading',
  },
  {
    id: 'allocation',
    title: 'Book · allocation',
    eyebrow: '03',
    chromePath: '/house/brief/book',
    columns: 4,
    state: 'loading',
  },
  {
    id: 'movers',
    title: 'Book · movers',
    eyebrow: '04',
    chromePath: '/house/brief/movers',
    columns: 4,
    state: 'loading',
  },
  {
    id: 'breaks',
    title: 'What could break the view',
    eyebrow: '05',
    chromePath: '/house/brief/breaks',
    columns: 4,
    state: 'loading',
  },
  {
    id: 'gloomberg-quotes',
    title: 'Gloomberg · quote strip',
    eyebrow: '06',
    chromePath: '/house/brief/gloomberg',
    columns: 8,
    state: 'loading',
  },
  {
    id: 'gloomberg-tape',
    title: 'Gloomberg · tape',
    eyebrow: '07',
    chromePath: '/house/brief/gloomberg',
    columns: 4,
    state: 'loading',
  },
  {
    id: 'luxalgo',
    title: 'LuxAlgo',
    eyebrow: '08',
    chromePath: '/house/brief/luxalgo',
    columns: 12,
    state: 'loading',
  },
  {
    id: 'run',
    title: 'Run health',
    eyebrow: '09',
    chromePath: '/house/brief/run',
    columns: 12,
    state: 'loading',
  },
];
