/**
 * @vitest-environment happy-dom
 */
import { Profiler, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
import { PageHeaderProvider, usePageHeader, usePageLayout } from './page-header';

let root: Root | null = null;
let host: HTMLElement | null = null;
let renders = 0;

function Page() {
  usePageHeader({ title: 'Settings', layout: 'fluid' });
  return null;
}

function LayoutProbe() {
  return <span data-testid="layout">{usePageLayout()}</span>;
}

const countRender = () => {
  renders += 1;
  if (renders > 50) throw new Error('page header never settled');
};

describe('usePageHeader (happy-dom)', () => {
  afterEach(() => {
    act(() => root?.unmount());
    host?.remove();
    root = null;
    host = null;
    renders = 0;
  });

  it('registers the spec once and settles instead of re-registering forever', async () => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
    await act(async () => {
      root!.render(
        <Profiler id="page-header" onRender={countRender}>
          <PageHeaderProvider>
            <Page />
            <LayoutProbe />
          </PageHeaderProvider>
        </Profiler>,
      );
    });
    expect(host.querySelector('[data-testid="layout"]')?.textContent).toBe('fluid');
    expect(renders).toBeLessThan(5);
  });
});
