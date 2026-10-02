/**
 * Desk shell feature flag.
 *
 * `NEXT_PUBLIC_DESK_SHELL=1` turns on the one-viewport desk shell.
 * Any other value, including unset, keeps the current scrolling shell.
 * Default is off until Brief panes mount, so a shell-only deploy does not
 * replace the paying brief with an empty terminal.
 *
 * `NEXT_PUBLIC_*` is inlined at build time. The dashboard is a static export
 * (`output: 'export'`), so a request-time env change does not flip the flag.
 * Set it in the build environment and rebuild. Do not add a Node BFF to
 * toggle it per request.
 */
export function isDeskShellEnabled(
  env: string | undefined = process.env.NEXT_PUBLIC_DESK_SHELL,
): boolean {
  return env === '1';
}
