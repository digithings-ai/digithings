/**
 * D9 recorded TUI frame preview (DIG-2698).
 *
 * TUIs export recorded frames with OpenTUI `captureCharFrame()`; the dashboard
 * renders them as Geist Mono text. Recorded frames only — no live socket in 1.0
 * (ADR D7): the frame is data, rendered byte-for-byte, never interpreted.
 *
 * The records are committed artifacts under `fixtures/tui-frames/`, written by
 * `clients/digiquant-tui/src/export-frame.ts`. A recorded frame carries the
 * moment it was taken, so the dashboard labels it with that moment — it is a
 * snapshot of a terminal, not a live terminal.
 */

/** One recorded terminal frame, exactly as the exporter wrote it. */
export type RecordedTuiFrame = {
  /** Which TUI the frame was recorded from (label only). */
  source: string;
  /** Desk path the frame was captured on (e.g. `/brief`). */
  path: string;
  /** ISO timestamp of the capture. */
  capturedAt: string;
  /** Captured width in terminal columns. */
  width: number;
  /** Captured height in terminal rows. */
  height: number;
  /** Recorded frame text, byte-for-byte as `captureCharFrame()` returned it. */
  frame: string;
};

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
 * A capture time must carry an explicit zone (`Z` or `±HH:MM`). An offset-less
 * timestamp is read in the machine's local zone, so the server render and the
 * client hydration would label the same frame with different times.
 */
const ZONED_ISO = /(?:Z|[+-]\d{2}:?\d{2})$/i;

/** True when the value is a complete recorded frame. */
export function isRecordedTuiFrame(value: unknown): value is RecordedTuiFrame {
  if (!value || typeof value !== 'object') return false;
  const record = value as Partial<RecordedTuiFrame>;
  return (
    typeof record.source === 'string' &&
    record.source.trim() !== '' &&
    typeof record.path === 'string' &&
    record.path.trim() !== '' &&
    typeof record.capturedAt === 'string' &&
    record.capturedAt.trim() !== '' &&
    ZONED_ISO.test(record.capturedAt.trim()) &&
    typeof record.width === 'number' &&
    Number.isFinite(record.width) &&
    record.width > 0 &&
    typeof record.height === 'number' &&
    Number.isFinite(record.height) &&
    record.height > 0 &&
    typeof record.frame === 'string' &&
    record.frame.length > 0
  );
}

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
