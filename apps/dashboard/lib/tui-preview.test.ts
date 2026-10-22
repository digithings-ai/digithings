import { describe, expect, it } from 'vitest';

import {
  formatRecordedTuiFrameDate,
  isRecordedTuiFrame,
  isTuiPreviewEnabled,
  readRecordedTuiFrames,
  tuiPreviewEnvFromProcess,
} from './tui-preview';

const RECORD = {
  source: 'digiquant-tui',
  path: '/brief',
  capturedAt: '2026-10-22T03:05:43.618Z',
  width: 64,
  height: 26,
  frame: '┌─────┐\n│ ok  │\n└─────┘',
};

describe('tuiPreviewEnvFromProcess', () => {
  it('exposes direct NEXT_PUBLIC_DIGI_TUI_PREVIEW for Turbopack inlining', () => {
    // House pattern (lib/digichat-popup.test.ts): the key must be read as
    // `process.env.NEXT_PUBLIC_DIGI_TUI_PREVIEW`, not by bracket access, or
    // Next does not inline it and the kill switch never reaches the bundle.
    expect(Object.keys(tuiPreviewEnvFromProcess()).sort()).toEqual(
      ['NEXT_PUBLIC_DIGI_TUI_PREVIEW'],
    );
  });
});

describe('tui preview', () => {
  it('is enabled by default and off only on the explicit kill switch', () => {
    expect(isTuiPreviewEnabled({})).toBe(true);
    expect(isTuiPreviewEnabled({ NEXT_PUBLIC_DIGI_TUI_PREVIEW: '1' })).toBe(true);
    expect(isTuiPreviewEnabled({ NEXT_PUBLIC_DIGI_TUI_PREVIEW: '0' })).toBe(false);
  });

  it('accepts a complete recorded frame', () => {
    expect(isRecordedTuiFrame(RECORD)).toBe(true);
  });

  it('rejects a frame that is missing a field or carries the wrong type', () => {
    expect(isRecordedTuiFrame(null)).toBe(false);
    expect(isRecordedTuiFrame('frame')).toBe(false);
    expect(isRecordedTuiFrame({ ...RECORD, source: '' })).toBe(false);
    expect(isRecordedTuiFrame({ ...RECORD, path: '' })).toBe(false);
    expect(isRecordedTuiFrame({ ...RECORD, capturedAt: '' })).toBe(false);
    expect(isRecordedTuiFrame({ ...RECORD, width: 0 })).toBe(false);
    expect(isRecordedTuiFrame({ ...RECORD, height: Number.NaN })).toBe(false);
    expect(isRecordedTuiFrame({ ...RECORD, frame: '' })).toBe(false);
    expect(isRecordedTuiFrame({ ...RECORD, width: '64' })).toBe(false);
  });

  it('rejects a capture time with no zone, so server and client cannot disagree', () => {
    expect(isRecordedTuiFrame({ ...RECORD, capturedAt: '2026-10-22T03:05:43.618' })).toBe(
      false,
    );
    expect(isRecordedTuiFrame({ ...RECORD, capturedAt: '2026-10-22 03:05' })).toBe(false);
    expect(isRecordedTuiFrame({ ...RECORD, capturedAt: '2026-10-22T03:05:43.618Z' })).toBe(
      true,
    );
    expect(
      isRecordedTuiFrame({ ...RECORD, capturedAt: '2026-10-22T05:05:43.618+02:00' }),
    ).toBe(true);
  });

  it('keeps the valid records of a list and drops the malformed ones', () => {
    const frames = readRecordedTuiFrames([RECORD, { source: 'broken' }, null, RECORD]);
    expect(frames).toHaveLength(2);
    expect(frames[0]?.source).toBe('digiquant-tui');
  });

  it('reads no frames from a value that is not a list', () => {
    expect(readRecordedTuiFrames(RECORD)).toEqual([]);
    expect(readRecordedTuiFrames(undefined)).toEqual([]);
  });

  it('labels the capture time in UTC, the same on server and client', () => {
    // The offset case distinguishes UTC from local getters even on a runner
    // whose clock is UTC: 05:05+02:00 is 03:05Z, but 05:05 local.
    expect(formatRecordedTuiFrameDate('2026-10-22T03:05:43.618Z')).toBe('2026-10-22 03:05Z');
    expect(formatRecordedTuiFrameDate('2026-10-22T05:05:43.618+02:00')).toBe('2026-10-22 03:05Z');
  });

  it('shows the raw value when the capture time cannot be parsed', () => {
    expect(formatRecordedTuiFrameDate('not a date')).toBe('not a date');
  });
});
