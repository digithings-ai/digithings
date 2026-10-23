'use client';

/**
 * D9 recorded-frame preview surface: TUIs (DIG-2698).
 *
 * Renders the committed recorded frames (OpenTUI `captureCharFrame()` output)
 * as Geist Mono text inside the dashboard shell. Recorded frames only — no live
 * socket in 1.0 (ADR D7) — so this surface needs no service, no entitlement and
 * no CSP change.
 *
 * The frame is data: it is rendered byte-for-byte, never interpreted. The
 * capture time is on the label, because a recorded frame is a snapshot of a
 * terminal, not a live terminal.
 */

import TuiFramePreview from '@/components/tui-frame-preview';
import digichatTuiFrame from '@/fixtures/tui-frames/digichat-tui.json';
import digiquantTuiFrame from '@/fixtures/tui-frames/digiquant-tui.json';
import {
  formatRecordedTuiFrameDate,
  isTuiPreviewEnabled,
  readRecordedTuiFrames,
  tuiPreviewEnvFromProcess,
  type RecordedTuiFrame,
} from '@/lib/tui-preview';

/** Committed recorded frames, one per TUI that ships an exporter. */
const COMMITTED_FRAMES: unknown[] = [digiquantTuiFrame, digichatTuiFrame];

// The pointer cursor belongs to the disclosure affordance. packages/ui owns no
// summary primitive, so it cannot carry the cursor for this surface.
const SUMMARY_CLASS = 'cursor-pointer text-[10px] font-medium uppercase tracking-widest text-ink-mute'; // canon-allow: app-local disclosure affordance

type TuiRecordedFramesProps = {
  /** Test override — production reads the committed artifacts. */
  frames?: unknown;
  /** Test override — production reads the process env. */
  env?: Record<string, string | undefined>;
};

export default function TuiRecordedFrames({
  frames = COMMITTED_FRAMES,
  env,
}: TuiRecordedFramesProps = {}) {
  if (!isTuiPreviewEnabled(env ?? tuiPreviewEnvFromProcess())) return null;
  const records: RecordedTuiFrame[] = readRecordedTuiFrames(frames);
  if (records.length === 0) return null;

  return (
    <section data-tui-recorded-frames="recorded" className="border-b border-hair px-3 py-2">
      {records.map((record) => (
        <details key={`${record.source}:${record.path}:${record.capturedAt}`}>
          <summary className={SUMMARY_CLASS}>
            {record.source} · {record.path} · recorded{' '}
            {formatRecordedTuiFrameDate(record.capturedAt)}
          </summary>
          <div className="mt-2 overflow-x-auto">
            <TuiFramePreview source={record.source} frame={record.frame} />
          </div>
        </details>
      ))}
    </section>
  );
}
