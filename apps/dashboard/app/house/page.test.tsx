/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const replace = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
}));

import HousePage from './page';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe('HousePage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replace.mockClear();
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

  it('redirects to Brief and does not render Corpus / Book / Profile', () => {
    act(() => {
      root.render(createElement(HousePage));
    });
    expect(replace).toHaveBeenCalledWith('/');
    expect(container.textContent).toContain('Redirecting to Brief');
    expect(container.textContent).not.toMatch(/Corpus|Profile/);
  });
});
