'use client';

import type { DragEvent, PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import { Button } from '@digithings/ui/ui';
import { resizePaneColumns, type PaneColumns } from '@/lib/desk/layout-store';
import type { DeskPaneModel } from '@/components/desk/shell/types';

export function PaneFrame({
  pane,
  columns,
  fullscreen,
  canMoveEarlier,
  canMoveLater,
  onFullscreen,
  onMove,
  onResize,
  onDragStart,
  onDragOver,
  onDrop,
  children,
}: {
  pane: DeskPaneModel;
  columns: PaneColumns;
  fullscreen: boolean;
  canMoveEarlier: boolean;
  canMoveLater: boolean;
  onFullscreen: (id: string | null) => void;
  onMove: (fromId: string, toId: string) => void;
  onResize: (id: string, columns: PaneColumns) => void;
  onDragStart: (event: DragEvent<HTMLElement>, id: string) => void;
  onDragOver: (event: DragEvent<HTMLElement>) => void;
  onDrop: (event: DragEvent<HTMLElement>, id: string) => void;
  children: ReactNode;
}) {
  const onResizePointer = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const startX = event.clientX;
    const start = columns;
    const width = event.currentTarget.parentElement?.parentElement?.clientWidth ?? 1;
    const columnWidth = Math.max(width / 12, 1);
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    const move = (ev: PointerEvent) => {
      const delta = Math.round((ev.clientX - startX) / columnWidth);
      onResize(pane.id, resizePaneColumns(start, delta));
    };
    const up = () => {
      target.removeEventListener('pointermove', move);
      target.removeEventListener('pointerup', up);
    };
    target.addEventListener('pointermove', move);
    target.addEventListener('pointerup', up);
  };

  return (
    <article
      data-pane-id={pane.id}
      data-pane-state={pane.state}
      data-pane-fullscreen={fullscreen ? 'true' : 'false'}
      data-chrome-path={pane.chromePath}
      onDragOver={onDragOver}
      onDrop={(event) => onDrop(event, pane.id)}
      className={`flex min-h-0 min-w-0 flex-col border border-hair bg-bg ${
        fullscreen ? 'fixed inset-0 z-40' : ''
      }`}
      style={fullscreen ? undefined : { gridColumn: `span ${columns} / span ${columns}` }}
    >
      <header
        draggable
        onDragStart={(event) => onDragStart(event, pane.id)}
        className="flex h-8 shrink-0 items-center gap-2 border-b border-hair bg-surface px-2"
      >
        <p className="font-mono text-[0.68rem] tracking-[0.08em] text-ink-mute uppercase">
          {pane.eyebrow}
          <span className="px-1 text-ink-mute">/</span>
          <span className="text-ink">{pane.title}</span>
        </p>
        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Move ${pane.title} earlier`}
            disabled={!canMoveEarlier}
            onClick={() => onMove(pane.id, 'earlier')}
          >
            ↑
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Move ${pane.title} later`}
            disabled={!canMoveLater}
            onClick={() => onMove(pane.id, 'later')}
          >
            ↓
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Narrow ${pane.title}`}
            onClick={() => onResize(pane.id, resizePaneColumns(columns, -1))}
          >
            –
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Widen ${pane.title}`}
            onClick={() => onResize(pane.id, resizePaneColumns(columns, 1))}
          >
            +
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label={fullscreen ? `Exit fullscreen ${pane.title}` : `Fullscreen ${pane.title}`}
            onClick={() => onFullscreen(fullscreen ? null : pane.id)}
          >
            {fullscreen ? 'Exit' : 'Full'}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Resize ${pane.title}`}
            onPointerDown={onResizePointer}
          >
            ‖
          </Button>
        </div>
      </header>
      <div data-pane-body="" className="min-h-0 flex-1 overflow-auto p-3">
        {pane.state === 'error' ? (
          <p role="alert" className="font-mono text-sm text-ink">
            {pane.errorMessage ?? 'This pane could not load.'}
          </p>
        ) : null}
        {pane.state === 'loading' ? (
          <p className="font-mono text-sm text-ink-mute">Loading…</p>
        ) : null}
        {children}
      </div>
    </article>
  );
}
