/**
 * D9 recorded TUI frame preview (DIG-2698).
 *
 * TUIs export recorded frames with OpenTUI `captureCharFrame()`; the dashboard
 * renders them as Geist Mono text. Recorded frames only — no live socket in 1.0
 * (ADR D7): the frame is data, rendered byte-for-byte, never interpreted.
 *
 * The records are committed artifacts under `fixtures/tui-frames/`, written by
 * the exporters in `clients/digiquant-tui` and `clients/digichat-tui`. The
 * record itself is declared once, in `@digithings/tui-frame`, so the dashboard
 * and the producers cannot drift on what a field means.
 */

import { isRecordedFrame, type RecordedFrame } from '@digithings/tui-frame';

/**
 * One recorded terminal frame, exactly as the exporter wrote it.
 *
 * `width` and `height` are the ink extent of the cropped frame, not the
 * terminal the client was rendered at: a 100-column terminal whose pane ends at
 * column 70 records width 70.
 */
export type RecordedTuiFrame = RecordedFrame;

/** Kill switch for the recorded-frame preview. Default on, `0` turns it off. */
export const TUI_PREVIEW_ENV_VAR = 'NEXT_PUBLIC_DIGI_TUI_PREVIEW';

/**
 * Direct `process.env.NEXT_PUBLIC_*` reads so Turbopack/Next can inline them
 * into the client bundle (same pattern as `lib/digichat-popup.ts`).
 */
export function tuiPreviewEnvFromProcess(): Record<string, string | undefined> {
  return {
    NEXT_PUBLIC_DIGI_TUI_PREVIEW: process.env.NEXT_PUBLIC_DIGI_TUI_PREVIEW,
  };
}

/**
 * Default on: the preview renders committed frames, so it needs no service and
 * no entitlement. `NEXT_PUBLIC_DIGI_TUI_PREVIEW=0` removes it from the shell.
 */
export function isTuiPreviewEnabled(
  env: Record<string, string | undefined> = tuiPreviewEnvFromProcess(),
): boolean {
  return env[TUI_PREVIEW_ENV_VAR] !== '0';
}

/**
 * True when the value is a complete recorded frame.
 *
 * The guard lives with the record in `@digithings/tui-frame`; the dashboard
 * keeps the name its call sites use. The zone rule it carries matters here:
 * an offset-less timestamp is read in the machine's local zone, so the server
 * render and the client hydration would label the same frame differently.
 */
export const isRecordedTuiFrame = isRecordedFrame;

/** Keep the valid records of a list, drop anything malformed. */
export function readRecordedTuiFrames(values: unknown): RecordedTuiFrame[] {
  if (!Array.isArray(values)) return [];
  return values.filter(isRecordedTuiFrame);
}

/**
 * Capture time as `YYYY-MM-DD HH:MMZ`. UTC getters only, so the server render
 * and the client hydration always agree.
 */
export function formatRecordedTuiFrameDate(capturedAt: string): string {
  const raw = capturedAt.trim();
  const parsed = Date.parse(raw);
  if (Number.isNaN(parsed)) return raw;
  const date = new Date(parsed);
  const pad = (value: number): string => String(value).padStart(2, '0');
  return (
    `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}` +
    ` ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}Z`
  );
}
