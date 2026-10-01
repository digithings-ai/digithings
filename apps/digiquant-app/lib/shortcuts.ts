/** Keyboard map — single source for the handler in Shell and the `?` help overlay. */
export type Shortcut = { keys: string; does: string };

export const SHORTCUTS: Shortcut[] = [
  { keys: '/  or  ⌘K', does: 'Go to any page (command line)' },
  { keys: '↑ ↓ Enter', does: 'Move / open in the command list' },
  { keys: '[', does: 'Pin or unpin the sidebar' },
  { keys: 'Esc', does: 'Close menu, list or this help' },
  { keys: 'e', does: 'Edit page layout (drag to move, corner to resize)' },
  { keys: 'arrows / ⇧ arrows', does: 'In layout edit: move / resize the focused block; Del removes it' },
  { keys: '?', does: 'Show shortcuts' },
  { keys: 'drag edge', does: 'Resize the sidebar; drag past the minimum to hide it' },
];
