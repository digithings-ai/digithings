/**
 * @vitest-environment happy-dom
 */
import { Profiler, act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
import { PageHeaderProvider, usePageHeader, usePageLayout } from './page-header';

let root: Root | null = null;
let host: HTMLElement | null = null;
let renders = 0;

function SettingsLikePage() {
  usePageHeader({ title: 'Settings', layout: 'fluid' });
  return null;
}

/** Fresh crumbs array and actions element every render — must still settle. */
function InlineSpecPage() {
  usePageHeader({
    title: 'Dossier',
    layout: 'fluid',
    crumbs: [{ label: 'Portfolio', href: '/portfolio' }],
    actions: <button type="button">Export</button>,
  });
  return null;
}

function LayoutProbe() {
  return <span data-testid="layout">{usePageLayout()}</span>;
}

const countRender = () => {
  renders += 1;
  if (renders > 50) throw new Error('page header never settled');
};

async function mount(page: ReactNode): Promise<HTMLElement> {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(
      <Profiler id="page-header" onRender={countRender}>
        <PageHeaderProvider>
          {page}
          <LayoutProbe />
        </PageHeaderProvider>
      </Profiler>,
    );
  });
  return host;
}

describe('usePageHeader (happy-dom)', () => {
  afterEach(() => {
    act(() => root?.unmount());
    host?.remove();
    root = null;
    host = null;
    renders = 0;
  });

  it('registers the spec once and settles instead of re-registering forever', async () => {
    const el = await mount(<SettingsLikePage />);
    expect(el.querySelector('[data-testid="layout"]')?.textContent).toBe('fluid');
    expect(renders).toBeLessThan(5);
  });

  it('settles when crumbs and actions are fresh objects on every page render', async () => {
    const el = await mount(<InlineSpecPage />);
    expect(el.querySelector('[data-testid="layout"]')?.textContent).toBe('fluid');
    expect(renders).toBeLessThan(5);
  });
});
