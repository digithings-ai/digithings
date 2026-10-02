/** Frozen pane contract. Pane seats import this and do not restyle the frame. */

export type PaneState = 'loading' | 'empty' | 'error' | 'ready';

export type DeskPaneModel = {
  id: string;
  title: string;
  chromePath: string;
  eyebrow: string;
  state: PaneState;
  errorMessage?: string;
  /** 4 | 5 | 6 | 7 | 8 | 12. Omitted spans the grid. */
  columns?: number;
};
