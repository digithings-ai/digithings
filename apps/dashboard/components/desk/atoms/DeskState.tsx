/**
 * TODO(slice-b): replace with `components/desk/atoms/DeskState.tsx` from
 * Slice B. Same states: loading, empty, error, ready.
 */
import type { ReactNode } from 'react';

export type PaneState = 'loading' | 'empty' | 'error' | 'ready';

const EMPTY = 'Empty until a run commits.';
const LOADING = 'Waiting on the run.';
const ERROR = 'Withheld. The run failed.';

export function DeskState({
  state,
  errorMessage,
  emptyLabel = EMPTY,
  loadingLabel = LOADING,
  children,
}: {
  state: PaneState;
  errorMessage?: string;
  emptyLabel?: string;
  loadingLabel?: string;
  children?: ReactNode;
}) {
  if (state === 'loading') {
    return (
      <p data-testid="pane-loading" role="status" className="px-3 py-3 text-xs text-ink-mute">
        {loadingLabel}
      </p>
    );
  }
  if (state === 'error') {
    return (
      <div data-testid="pane-error" className="px-3 py-3 text-xs text-ink">
        <p>{ERROR}</p>
        {errorMessage ? <p className="mt-1 text-ink-mute">{errorMessage}</p> : null}
      </div>
    );
  }
  if (state === 'empty') {
    return (
      <p data-testid="pane-empty" className="px-3 py-3 text-xs text-ink-mute">
        {emptyLabel}
      </p>
    );
  }
  return <>{children}</>;
}
