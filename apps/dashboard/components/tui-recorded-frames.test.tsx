/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import TuiRecordedFrames from './tui-recorded-frames';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const FRAME = '┌──────────────┐\n│ Brief        │\n└──────────────┘';

const RECORD = {
  source: 'digiquant-tui',
  path: '/brief',
  capturedAt: '2026-10-22T03:05:43.618Z',
  width: 64,
  height: 26,
  frame: FRAME,
};

describe('TuiRecordedFrames', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('renders the recorded frame in monospace with its capture time', () => {
    act(() => {
      root.render(createElement(TuiRecordedFrames, { frames: [RECORD] }));
    });
    const section = container.querySelector('[data-tui-recorded-frames="recorded"]');
    expect(section).not.toBeNull();
    const pre = section!.querySelector('pre.font-mono');
    expect(pre!.textContent).toBe(FRAME);
    const summary = section!.querySelector('summary')!;
    expect(summary.textContent).toContain('digiquant-tui');
    expect(summary.textContent).toContain('/brief');
    expect(summary.textContent).toContain('2026-10-22 03:05Z');
  });

  it('renders nothing when the kill switch is off', () => {
    act(() => {
      root.render(
        createElement(TuiRecordedFrames, {
          frames: [RECORD],
          env: { NEXT_PUBLIC_DIGI_TUI_PREVIEW: '0' },
        }),
      );
    });
    expect(container.querySelector('[data-tui-recorded-frames]')).toBeNull();
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when every record is malformed', () => {
    act(() => {
      root.render(createElement(TuiRecordedFrames, { frames: [{ source: 'broken' }] }));
    });
    expect(container.querySelector('[data-tui-recorded-frames]')).toBeNull();
  });

  it('renders the committed artifact by default', () => {
    act(() => {
      root.render(createElement(TuiRecordedFrames, {}));
    });
    const pre = container.querySelector('pre.font-mono');
    expect(pre).not.toBeNull();
    expect(pre!.textContent).toContain('Brief');
    // Every committed frame reaches the desk pane, not only the one imported
    // first: the dashboard copy of the digichat frame is easy to forget.
    const summaries = Array.from(container.querySelectorAll('summary')).map(
      (node) => node.textContent ?? '',
    );
    expect(summaries.some((text) => text.includes('digichat-tui'))).toBe(true);
    // The committed artifact is a fixture capture, not a loading or error
    // state: the exporter refuses to write a frame that still says
    // "loading…" or "could not be reached".
    expect(pre!.textContent).not.toContain('loading…');
    expect(pre!.textContent).not.toContain('could not be reached');
  });

  it('ships the block collapsed, so the shell stays quiet until it is opened', () => {
    act(() => {
      root.render(createElement(TuiRecordedFrames, { frames: [RECORD] }));
    });
    const details = container.querySelector('details')!;
    expect(details).not.toBeNull();
    expect(details.hasAttribute('open')).toBe(false);
    expect(details.open).toBe(false);
  });

  it('renders a frame that carries HTML metacharacters as text, never as markup', () => {
    const hostile = {
      ...RECORD,
      frame: '<script>window.__pwned = 1</script><img src=x onerror="window.__pwned=1">',
    };
    act(() => {
      root.render(createElement(TuiRecordedFrames, { frames: [hostile] }));
    });
    const pre = container.querySelector('pre.font-mono')!;
    expect(pre.textContent).toBe(hostile.frame);
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
  });

  it('renders two records of the same source and path under different keys', () => {
    const later = { ...RECORD, capturedAt: '2026-10-23T04:06:44.719Z' };
    act(() => {
      root.render(createElement(TuiRecordedFrames, { frames: [RECORD, later] }));
    });
    const details = container.querySelectorAll('details');
    expect(details).toHaveLength(2);
    const labels = Array.from(details).map((d) => d.querySelector('summary')!.textContent);
    expect(labels[0]).toContain('2026-10-22 03:05Z');
    expect(labels[1]).toContain('2026-10-23 04:06Z');
  });
});
