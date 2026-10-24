/**
 * Same switch Slice A uses for the desk shell (`NEXT_PUBLIC_DESK_SHELL`).
 * Default off so a shell-only or pane-only deploy does not replace the
 * current Brief. Inlined at build time, like every other `NEXT_PUBLIC_*`.
 */
export function deskShellEnabled(): boolean {
  return process.env.NEXT_PUBLIC_DESK_SHELL === '1';
}
