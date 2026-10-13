import type { ReactNode } from 'react';
import type { PaneState } from '@/lib/desk/types';
import { DeskPaneChrome } from './DeskPaneChrome';
import { DeskState } from './DeskState';

export interface DeskPipelineFrameProps {
  state: PaneState;
  errorMessage?: string;
  emptyMessage?: string;
  eyebrow?: string;
  title?: string;
  chromePath?: string;
  children?: ReactNode;
}

/**
 * Pipeline pane frame. Loading and error replace the body so a failed run
 * is not a spinner painted over the last success.
 */
export function DeskPipelineFrame({
  state,
  errorMessage,
  emptyMessage = 'No run for this date',
  eyebrow = '01',
  title = 'Run health',
  chromePath = '/house/pipeline',
  children,
}: DeskPipelineFrameProps) {
  return (
    <DeskPaneChrome eyebrow={eyebrow} title={title} chromePath={chromePath}>
      <div data-testid="desk-pipeline-frame">
        <DeskState state={state} errorMessage={errorMessage} emptyMessage={emptyMessage}>
          {children}
        </DeskState>
      </div>
    </DeskPaneChrome>
  );
}
