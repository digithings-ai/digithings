/**
 * Frozen pane contract from the dashboard wire-up plan (§5).
 * Slice A owns the shell that mounts these; slice B owns the data atoms.
 */

export type PaneState = 'loading' | 'empty' | 'error' | 'ready';

export type DeskPaneModel = {
  id: string;
  /** "Book · movers" */
  title: string;
  /** "/house/brief/movers" */
  chromePath: string;
  /** "04" */
  eyebrow: string;
  state: PaneState;
  errorMessage?: string;
  /** 4 | 5 | 6 | 7 | 8 | 12 */
  columns?: number;
};
