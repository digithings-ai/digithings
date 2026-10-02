/** Session pane order and column spans. Slice A scaffolding; pane seats reuse it. */

export const DESK_LAYOUT_STORAGE_KEY = 'dashboard-desk-layout';

export const PANE_COLUMN_STEPS = [4, 5, 6, 7, 8, 12] as const;
export type PaneColumns = (typeof PANE_COLUMN_STEPS)[number];

export type StoredPaneLayout = {
  id: string;
  columns: PaneColumns;
  order: number;
};

export type DeskLayoutSnapshot = {
  panes: StoredPaneLayout[];
};

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

function isPaneColumns(value: unknown): value is PaneColumns {
  return (PANE_COLUMN_STEPS as readonly number[]).includes(value as number);
}

export function paneColumnsOrDefault(value: number | undefined): PaneColumns {
  return isPaneColumns(value) ? value : 12;
}

export function resizePaneColumns(current: number, delta: number): PaneColumns {
  const steps = PANE_COLUMN_STEPS;
  let index = steps.findIndex((step) => step === current);
  if (index < 0) {
    index = steps.reduce(
      (best, step, i) =>
        Math.abs(step - current) < Math.abs(steps[best] - current) ? i : best,
      0,
    );
  }
  const next = Math.min(steps.length - 1, Math.max(0, index + delta));
  return steps[next];
}

export function reorderPanes<T extends { id: string; order: number }>(
  panes: readonly T[],
  fromId: string,
  toId: string,
): T[] {
  if (fromId === toId) return [...panes];
  const sorted = [...panes].sort((a, b) => a.order - b.order);
  const from = sorted.findIndex((pane) => pane.id === fromId);
  const to = sorted.findIndex((pane) => pane.id === toId);
  if (from < 0 || to < 0) return [...panes];
  const [moved] = sorted.splice(from, 1);
  if (!moved) return [...panes];
  sorted.splice(to, 0, moved);
  return sorted.map((pane, order) => ({ ...pane, order }));
}

export function defaultPaneLayout(ids: readonly string[]): StoredPaneLayout[] {
  return ids.map((id, order) => ({
    id,
    columns: 12,
    order,
  }));
}

export function readDeskLayout(storage: StorageLike | null): DeskLayoutSnapshot | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(DESK_LAYOUT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<DeskLayoutSnapshot>;
    if (!parsed || !Array.isArray(parsed.panes)) return null;
    const panes: StoredPaneLayout[] = [];
    for (const pane of parsed.panes) {
      if (!pane || typeof pane.id !== 'string' || !isPaneColumns(pane.columns)) continue;
      panes.push({
        id: pane.id,
        columns: pane.columns,
        order: typeof pane.order === 'number' ? pane.order : panes.length,
      });
    }
    return { panes };
  } catch {
    return null;
  }
}

const layoutListeners = new Set<() => void>();
let layoutSnapshotRaw: string | null | undefined;
let layoutSnapshotValue: DeskLayoutSnapshot | null = null;

export function subscribeDeskLayout(listener: () => void): () => void {
  layoutListeners.add(listener);
  return () => {
    layoutListeners.delete(listener);
  };
}

/** Client snapshot for useSyncExternalStore. Cached by the raw session string. */
export function getDeskLayoutSnapshot(): DeskLayoutSnapshot | null {
  if (typeof window === 'undefined') return null;
  let raw: string | null;
  try {
    raw = window.sessionStorage.getItem(DESK_LAYOUT_STORAGE_KEY);
  } catch {
    return null;
  }
  if (raw === layoutSnapshotRaw) return layoutSnapshotValue;
  layoutSnapshotRaw = raw;
  layoutSnapshotValue = readDeskLayout(window.sessionStorage);
  return layoutSnapshotValue;
}

export function getDeskLayoutServerSnapshot(): DeskLayoutSnapshot | null {
  return null;
}

function publishDeskLayout(): void {
  layoutSnapshotRaw = undefined;
  for (const listener of layoutListeners) listener();
}

export function writeDeskLayout(snapshot: DeskLayoutSnapshot, storage: StorageLike | null): void {
  if (!storage) return;
  try {
    storage.setItem(DESK_LAYOUT_STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    /* sessionStorage can throw in private mode; the in-memory layout still works. */
  }
  publishDeskLayout();
}

/** Apply a saved snapshot onto the current pane ids. Unknown saved ids drop out. */
export function mergePaneLayout(
  ids: readonly string[],
  saved: readonly StoredPaneLayout[] | null,
): StoredPaneLayout[] {
  const defaults = defaultPaneLayout(ids);
  if (!saved || saved.length === 0) return defaults;
  const byId = new Map(saved.map((pane) => [pane.id, pane]));
  const merged = defaults.map((pane) => {
    const stored = byId.get(pane.id);
    return stored ? { ...pane, columns: stored.columns, order: stored.order } : pane;
  });
  return merged
    .sort((a, b) => a.order - b.order)
    .map((pane, order) => ({ ...pane, order }));
}
