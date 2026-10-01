/** Keyboard map — single source for the handler in Shell and the `?` help overlay. */
export type Shortcut = { keys: string; does: string };

export const SHORTCUTS: Shortcut[] = [
  { keys: '/  or  ⌘K', does: 'Go to any page (command line)' },
  { keys: '↑ ↓ Enter', does: 'Move / open in the command list' },
  { keys: '[', does: 'Pin or unpin the sidebar' },
  { keys: 'Esc', does: 'Close menu, list or this help' },
  { keys: '?', does: 'Show shortcuts' },
  { keys: 'drag edge', does: 'Resize the sidebar; drag past the minimum to hide it' },
];
