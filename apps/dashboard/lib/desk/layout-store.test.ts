import { describe, expect, it } from 'vitest';
import {
  defaultPaneLayout,
  mergePaneLayout,
  readDeskLayout,
  reorderPanes,
  resizePaneColumns,
  writeDeskLayout,
  DESK_LAYOUT_STORAGE_KEY,
} from './layout-store';

describe('resizePaneColumns', () => {
  it('steps through the fixed column spans', () => {
    expect(resizePaneColumns(12, -1)).toBe(8);
    expect(resizePaneColumns(8, -1)).toBe(7);
    expect(resizePaneColumns(4, -1)).toBe(4);
    expect(resizePaneColumns(8, 1)).toBe(12);
    expect(resizePaneColumns(12, 1)).toBe(12);
  });

  it('snaps an unknown span to the nearest step before moving', () => {
    expect(resizePaneColumns(10, 1)).toBe(12);
    expect(resizePaneColumns(3, 1)).toBe(5);
  });
});

describe('reorderPanes', () => {
  const panes = [
    { id: 'a', order: 0 },
    { id: 'b', order: 1 },
    { id: 'c', order: 2 },
  ];

  it('moves a pane onto another id and rewrites order', () => {
    expect(reorderPanes(panes, 'c', 'a').map((pane) => pane.id)).toEqual(['c', 'a', 'b']);
    expect(reorderPanes(panes, 'a', 'c').map((pane) => pane.order)).toEqual([0, 1, 2]);
  });

  it('leaves the list alone for an unknown id', () => {
    expect(reorderPanes(panes, 'missing', 'a')).toEqual(panes);
  });
});

describe('desk layout session snapshot', () => {
  function memory() {
    const data = new Map<string, string>();
    return {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => {
        data.set(key, value);
      },
    };
  }

  it('round-trips pane columns and drops corrupt payloads', () => {
    const storage = memory();
    writeDeskLayout(
      { panes: [{ id: 'page', columns: 6, order: 0 }] },
      storage,
    );
    expect(storage.getItem(DESK_LAYOUT_STORAGE_KEY)).toContain('"columns":6');
    expect(readDeskLayout(storage)?.panes[0]).toMatchObject({ id: 'page', columns: 6 });
    storage.setItem(DESK_LAYOUT_STORAGE_KEY, '{');
    expect(readDeskLayout(storage)).toBeNull();
    expect(readDeskLayout(null)).toBeNull();
  });

  it('merges a saved span onto the live pane ids', () => {
    const merged = mergePaneLayout(
      ['page', 'extra'],
      [{ id: 'page', columns: 8, order: 2 }],
    );
    expect(merged.find((pane) => pane.id === 'page')?.columns).toBe(8);
    expect(merged.map((pane) => pane.id)).toEqual(['extra', 'page']);
    expect(defaultPaneLayout(['page'])[0].columns).toBe(12);
  });
});
