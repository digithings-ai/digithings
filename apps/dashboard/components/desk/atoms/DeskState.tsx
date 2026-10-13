import type { ReactNode } from 'react';
import type { PaneState } from '@/lib/desk/types';

export type { PaneState };

export interface DeskStateProps {
  state: PaneState;
  errorMessage?: string;
  emptyMessage?: string;
  /** Brief panes pass this name. Same text as `emptyMessage`. */
  emptyLabel?: string;
  loadingMessage?: string;
  /** Brief panes pass this name. Same text as `loadingMessage`. */
  loadingLabel?: string;
  children?: ReactNode;
}

/**
 * Loading, empty, and error frames for a desk pane.
 * Ready renders children. The other states never invent a zero.
 */
export function DeskState({
  state,
  errorMessage,
  emptyMessage,
  emptyLabel,
  loadingMessage,
  loadingLabel,
  children,
}: DeskStateProps) {
  const emptyText = emptyMessage ?? emptyLabel ?? 'Nothing here yet';
  const loadingText = loadingMessage ?? loadingLabel ?? 'Loading';
  if (state === 'ready') return <>{children}</>;

  if (state === 'loading') {
    return (
      <div
        className="px-3 py-6 font-mono text-[11px] text-ink-mute"
        data-testid="desk-state-loading"
        role="status"
        aria-busy="true"
      >
        {loadingText}
      </div>
    );
  }

  if (state === 'empty') {
    return (
      <div className="px-3 py-6 font-mono text-[11px] text-ink-mute" data-testid="desk-state-empty">
        {emptyText}
      </div>
    );
  }

  return (
    <div className="px-3 py-6 font-mono text-[11px] text-down" data-testid="desk-state-error" role="alert">
      {errorMessage && errorMessage.length > 0 ? errorMessage : 'Request failed'}
    </div>
  );
}
