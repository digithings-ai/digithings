import type { ReactNode } from 'react';
import { formatOverlapGatedMetric } from '@/lib/desk/tearsheet-metrics';
import type { PaneState } from '@/lib/desk/types';
import { DeskPaneChrome } from './DeskPaneChrome';
import { DeskState } from './DeskState';

export interface DeskTearsheetFrameProps {
  state: PaneState;
  errorMessage?: string;
  emptyMessage?: string;
  eyebrow?: string;
  title?: string;
  chromePath?: string;
  overlapDays?: number;
  alphaPct?: number | null;
  informationRatio?: number | null;
  children?: ReactNode;
}

/** Tearsheet frame. Alpha and IR render an em dash under the overlap floor. */
export function DeskTearsheetFrame({
  state,
  errorMessage,
  emptyMessage = 'No tearsheet for this book',
  eyebrow = '03',
  title = 'Tearsheet',
  chromePath = '/house/portfolio/tearsheet',
  overlapDays = 0,
  alphaPct = null,
  informationRatio = null,
  children,
}: DeskTearsheetFrameProps) {
  return (
    <DeskPaneChrome eyebrow={eyebrow} title={title} chromePath={chromePath}>
      <div className="ts-panel" data-testid="desk-tearsheet-frame">
        <DeskState state={state} errorMessage={errorMessage} emptyMessage={emptyMessage}>
          <dl className="grid grid-cols-2 gap-2 px-3 py-2 font-mono text-[11px]">
            <div>
              <dt className="text-[10px] uppercase tracking-[0.12em] text-ink-mute">Alpha</dt>
              <dd data-testid="tearsheet-alpha">{formatOverlapGatedMetric(alphaPct, overlapDays)}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-[0.12em] text-ink-mute">IR</dt>
              <dd data-testid="tearsheet-ir">{formatOverlapGatedMetric(informationRatio, overlapDays)}</dd>
            </div>
          </dl>
          {children}
        </DeskState>
      </div>
    </DeskPaneChrome>
  );
}
