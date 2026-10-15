import type { PaneState } from '@/lib/desk/types';
import { DeskState } from './DeskState';

export interface DeskFeedItem {
  id: string;
  title: string;
  detail?: string | null;
  time?: string | null;
}

export interface DeskFeedProps {
  items: readonly DeskFeedItem[];
  state?: PaneState;
  errorMessage?: string;
  emptyMessage?: string;
}

/** Tape and trace rows. An empty list is an empty pane, not placeholder copy. */
export function DeskFeed({
  items,
  state,
  errorMessage,
  emptyMessage = 'No tape',
}: DeskFeedProps) {
  const viewState: PaneState = state ?? (items.length === 0 ? 'empty' : 'ready');
  return (
    <DeskState state={viewState} errorMessage={errorMessage} emptyMessage={emptyMessage}>
      <ol className="divide-y divide-hair" data-testid="desk-feed">
        {items.map((item) => (
          <li key={item.id} className="px-3 py-2 font-mono text-[11px]">
            {item.time ? <span className="mr-2 text-ink-mute">{item.time}</span> : null}
            <span className="text-ink">{item.title}</span>
            {item.detail ? <span className="mt-0.5 block text-ink-soft">{item.detail}</span> : null}
          </li>
        ))}
      </ol>
    </DeskState>
  );
}
