/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import TuiFramePreview from './tui-frame-preview';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const FRAME = '+-- TITLEWORD --+\n| body one      |\n| body two      |\n+---------------+';

describe('TuiFramePreview', () => {
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

  it('renders the recorded frame byte-for-byte in monospace', () => {
    act(() => {
      root.render(createElement(TuiFramePreview, { source: 'digiquant-tui', frame: FRAME }));
    });
    const section = container.querySelector('[data-tui-frame-preview="digiquant-tui"]');
    expect(section).not.toBeNull();
    const pre = section!.querySelector('pre.font-mono');
    expect(pre).not.toBeNull();
    expect(pre!.textContent).toBe(FRAME);
  });

  it('renders an empty pre for an empty frame, never nothing', () => {
    act(() => {
      root.render(createElement(TuiFramePreview, { source: 'digivoice', frame: '' }));
    });
    const pre = container.querySelector('[data-tui-frame-preview="digivoice"] pre');
    expect(pre).not.toBeNull();
    expect(pre!.textContent).toBe('');
  });
});
