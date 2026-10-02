'use client';

import type { DragEvent, ReactNode } from 'react';
import { PaneFrame } from '@/components/desk/shell/PaneFrame';
import {
  reorderPanes,
  type PaneColumns,
  type StoredPaneLayout,
} from '@/lib/desk/layout-store';
import type { DeskPaneModel } from '@/components/desk/shell/types';

export type DeskPaneSlot = DeskPaneModel & { children: ReactNode };

function neighborId(layout: readonly StoredPaneLayout[], id: string, direction: -1 | 1): string | null {
  const sorted = [...layout].sort((a, b) => a.order - b.order);
  const index = sorted.findIndex((pane) => pane.id === id);
  if (index < 0) return null;
  return sorted[index + direction]?.id ?? null;
}

export function PaneGrid({
  panes,
  layout,
  fullscreenId,
  onLayout,
  onFullscreen,
}: {
  panes: readonly DeskPaneSlot[];
  layout: readonly StoredPaneLayout[];
  fullscreenId: string | null;
  onLayout: (next: StoredPaneLayout[]) => void;
  onFullscreen: (id: string | null) => void;
}) {
  const ordered = [...panes].sort((a, b) => {
    const ao = layout.find((pane) => pane.id === a.id)?.order ?? 0;
    const bo = layout.find((pane) => pane.id === b.id)?.order ?? 0;
    return ao - bo;
  });

  const onDragStart = (event: DragEvent<HTMLElement>, id: string) => {
    event.dataTransfer.setData('text/plain', id);
    event.dataTransfer.effectAllowed = 'move';
  };

  const onDragOver = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
  };

  const onDrop = (event: DragEvent<HTMLElement>, targetId: string) => {
    event.preventDefault();
    const fromId = event.dataTransfer.getData('text/plain');
    if (!fromId || fromId === targetId) return;
    onLayout(reorderPanes(layout, fromId, targetId));
  };

  const onMove = (fromId: string, direction: string) => {
    const toId = neighborId(layout, fromId, direction === 'earlier' ? -1 : 1);
    if (!toId) return;
    onLayout(reorderPanes(layout, fromId, toId));
  };

  const onResize = (id: string, columns: PaneColumns) => {
    onLayout(layout.map((pane) => (pane.id === id ? { ...pane, columns } : pane)));
  };

  return (
    <div
      data-pane-grid=""
      className="grid h-full min-h-0 gap-px overflow-hidden"
      style={{ gridTemplateColumns: 'repeat(12, minmax(0, 1fr))' }}
    >
      {ordered.map((pane) => {
        const stored = layout.find((item) => item.id === pane.id);
        const columns = stored?.columns ?? 12;
        const hidden = fullscreenId !== null && fullscreenId !== pane.id;
        if (hidden) return null;
        const order = stored?.order ?? 0;
        const maxOrder = Math.max(...layout.map((item) => item.order));
        return (
          <PaneFrame
            key={pane.id}
            pane={pane}
            columns={columns}
            fullscreen={fullscreenId === pane.id}
            canMoveEarlier={order > 0}
            canMoveLater={order < maxOrder}
            onFullscreen={onFullscreen}
            onMove={onMove}
            onResize={onResize}
            onDragStart={onDragStart}
            onDragOver={onDragOver}
            onDrop={onDrop}
          >
            {pane.children}
          </PaneFrame>
        );
      })}
    </div>
  );
}
