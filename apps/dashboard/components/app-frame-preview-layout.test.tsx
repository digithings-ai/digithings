/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AppFrame from './app-frame';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));
vi.mock('@/components/sidebar', () => ({ default: () => null }));
vi.mock('@/components/mobile-app-bar', () => ({ default: () => null }));
vi.mock('@/components/command-palette', () => ({ default: () => null }));
vi.mock('@/components/digichat-popup', () => ({ default: () => null }));
vi.mock('@/components/db-unavailable', () => ({ default: () => null }));
vi.mock('@/components/fx-hub-only-guard', () => ({
  default: ({ children }: { children: unknown }) => children,
}));
vi.mock('@/components/desk/panes/brief', () => ({ deskShellEnabled: () => false }));
vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: () => ({ dbStatus: 'ok' }),
}));
vi.mock('@/components/digichat-live-preview', () => ({
  default: () => createElement('div', { 'data-testid': 'd8-preview' }),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/**
 * The D8 live preview must live inside the content column (DIG-5138).
 *
 * As a row sibling of <main> it took its max-content width and squeezed the
 * dashboard column to 38px on desktop and 0px on a 390px phone (QA,
 * DIG-5134). This test pins the placement, so the squeeze cannot come back:
 * the preview is a descendant of <main> and never a direct child of the
 * shell row.
 *
 * Two properties are pinned besides the placement, because "inside <main>" on
 * its own is not the same as "takes the column's width":
 *   - <main> keeps `min-w-0` and `flex-1`: the column may shrink instead of
 *     being sized by its content, and it takes the free width of the row.
 *   - nothing between the preview and <main> carries a fixed width or
 *     `shrink-0`: a `w-[300px]` wrapper is the original squeeze in a new
 *     place.
 */
describe('AppFrame preview placement', () => {
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

  it('mounts the D8 preview inside the content column, not beside it', () => {
    act(() => {
      root.render(
        createElement(AppFrame, null, createElement('p', null, 'page')),
      );
    });

    const shell = container.firstElementChild!;
    const directChildren = Array.from(shell.children).map((child) =>
      child.getAttribute('data-testid'),
    );
    expect(directChildren).not.toContain('d8-preview');

    const main = shell.querySelector('main')!;
    expect(main).not.toBeNull();
    expect(main.querySelector('[data-testid="d8-preview"]')).not.toBeNull();
  });

  it('keeps the content column shrinkable and full width', () => {
    act(() => {
      root.render(
        createElement(AppFrame, null, createElement('p', null, 'page')),
      );
    });

    const main = container.querySelector('main')!;
    // min-w-0: the column may shrink below its content width (without it the
    // column is sized by the content and the squeeze comes back).
    expect(main.className).toContain('min-w-0');
    // flex-1: the column takes the free width of the shell row.
    expect(main.className).toContain('flex-1');
  });

  it('puts no fixed width between the preview and the content column', () => {
    act(() => {
      root.render(
        createElement(AppFrame, null, createElement('p', null, 'page')),
      );
    });

    const main = container.querySelector('main')!;
    const preview = main.querySelector('[data-testid="d8-preview"]')!;
    let node: Element | null = preview.parentElement;
    while (node && node !== main) {
      const className = node.getAttribute('class') ?? '';
      expect(className).not.toMatch(/\bw-\[/);
      expect(className).not.toContain('shrink-0');
      node = node.parentElement;
    }
    expect(node).toBe(main);
  });
});
