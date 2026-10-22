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
vi.mock('@/components/tui-recorded-frames', () => ({
  default: () => createElement('div', { 'data-testid': 'd9-recorded' }),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/**
 * Every ancestor between `node` and `main` must be width-neutral.
 *
 * `w-full` and `w-max` in the same class list both satisfy a substring check,
 * and `w-max`, `w-fit`, `min-w-screen` and `min-w-[900px]` squeeze or overflow
 * the column exactly as a fixed width does, so this reads the class list as
 * tokens.
 */
function sizingViolations(node: Element, main: Element): string[] {
  const violations: string[] = [];
  let current: Element | null = node.parentElement;
  while (current && current !== main) {
    const className = current.getAttribute('class') ?? '';
    const widthTokens = className
      .split(/\s+/)
      .filter((token) => /^(min-|max-)?w-/.test(token));
    if (widthTokens.length > 0) violations.push(`width: ${widthTokens.join(' ')}`);
    if (className.includes('shrink-0')) violations.push('shrink-0');
    if (className.includes('flex-none')) violations.push('flex-none');
    current = current.parentElement;
  }
  if (current !== main) violations.push('not inside <main>');
  return violations;
}

/**
 * The D8 live preview must live inside the content column (DIG-5138).
 *
 * As a row sibling of <main> it took its max-content width and squeezed the
 * dashboard column to 38px on desktop and 0px on a 390px phone (QA,
 * DIG-5134). This test pins the placement, so the squeeze cannot come back:
 * the preview is a descendant of <main> and never a direct child of the
 * shell row.
 *
 * The D9 recorded-frame surface (DIG-2698, merged via #6264) also mounts
 * inside <main>. The merge that brought this branch up to develop had to keep
 * both surfaces; this test fails if either one is dropped or moved out.
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

  function renderFrame() {
    act(() => {
      root.render(createElement(AppFrame, null, createElement('p', null, 'page')));
    });
  }

  it('mounts the D8 preview inside the content column, not beside it', () => {
    renderFrame();

    const shell = container.firstElementChild!;
    const directChildren = Array.from(shell.children).map((child) =>
      child.getAttribute('data-testid'),
    );
    expect(directChildren).not.toContain('d8-preview');

    const main = shell.querySelector('main')!;
    expect(main).not.toBeNull();
    expect(main.querySelector('[data-testid="d8-preview"]')).not.toBeNull();
  });

  it('keeps both the D9 recorded frames and the D8 strip inside the column', () => {
    renderFrame();

    const main = container.querySelector('main')!;
    const recorded = main.querySelector('[data-testid="d9-recorded"]');
    const preview = main.querySelector('[data-testid="d8-preview"]');
    // Dropping either surface was the risk in the rebase: D9 had landed on
    // develop, D8 is this branch's change.
    expect(recorded).not.toBeNull();
    expect(preview).not.toBeNull();

    // Both sit above the page content, in the column, so the page is not
    // pushed down and neither strip is a row sibling of <main>.
    const order = Array.from(main.children);
    const pageWrapper = container.querySelector('p')!.parentElement!;
    expect(order.indexOf(recorded!)).toBeGreaterThanOrEqual(0);
    expect(order.indexOf(preview!)).toBeGreaterThan(order.indexOf(recorded!));
    expect(order.indexOf(preview!)).toBeLessThan(order.indexOf(pageWrapper));
  });

  it('keeps the content column shrinkable and full width', () => {
    renderFrame();

    const main = container.querySelector('main')!;
    // min-w-0: the column may shrink below its content width (without it the
    // column is sized by the content and the squeeze comes back).
    expect(main.className).toContain('min-w-0');
    // flex-1: the column takes the free width of the shell row.
    expect(main.className).toContain('flex-1');
  });

  it('puts no fixed width between the preview and the content column', () => {
    renderFrame();

    const main = container.querySelector('main')!;
    const preview = main.querySelector('[data-testid="d8-preview"]')!;
    expect(sizingViolations(preview, main)).toEqual([]);
  });

  it('catches a width-carrying wrapper between the preview and the column', () => {
    // The preview is a direct child of <main>, so the walk above has nothing
    // to visit in this tree. This fixture keeps the rule executing: a
    // `w-[300px] shrink-0` wrapper is the original squeeze in a new place,
    // and the checker must name it instead of passing trivially.
    const main = document.createElement('main');
    const pageWrapper = document.createElement('div');
    const wrapper = document.createElement('div');
    wrapper.className = 'w-[300px] shrink-0';
    const preview = document.createElement('div');
    wrapper.appendChild(preview);
    main.append(wrapper, pageWrapper);

    expect(sizingViolations(preview, main)).toEqual(['width: w-[300px]', 'shrink-0']);
    // A width-neutral wrapper is not a violation.
    wrapper.className = 'flex flex-col';
    expect(sizingViolations(preview, main)).toEqual([]);
  });

  it('mounts the preview directly in the column, above the page content', () => {
    renderFrame();

    const main = container.querySelector('main')!;
    const preview = main.querySelector('[data-testid="d8-preview"]')!;
    // Direct child: a wrapper between the preview and the column is where a
    // fixed width would hide.
    expect(preview.parentElement).toBe(main);
    // The strip sits above the page content, so the page is not pushed down.
    const page = container.querySelector('p')!;
    const order = Array.from(main.children);
    expect(order.indexOf(preview)).toBeLessThan(order.indexOf(page.parentElement!));
  });
});
