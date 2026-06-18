import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { fixtureEnvelope } from '@/lib/__fixtures__/snapshot-fixture';
import type { SnapshotFetchResult } from '@/lib/snapshot-types';

// Controllable hook result, hoisted so the vi.mock factory can close over it.
const holder = vi.hoisted(() => ({ result: null as SnapshotFetchResult | null }));

// Override only useLatestSnapshot; keep the real banners / sub-renderers the
// Morning Brief reuses so this exercises the actual render path.
vi.mock('./daily-snapshot-panel', async (importActual) => {
  const actual = await importActual<typeof import('./daily-snapshot-panel')>();
  return {
    ...actual,
    useLatestSnapshot: () => ({ result: holder.result, refetch: () => undefined }),
  };
});

// Imported after vi.mock so the mocked dependency is in place.
const { MorningBriefPanel } = await import('./morning-brief-panel');

function render(): string {
  return renderToStaticMarkup(createElement(MorningBriefPanel));
}

describe('MorningBriefPanel', () => {
  it('renders the loading skeleton while the snapshot is null', () => {
    holder.result = null;
    expect(render()).toContain('snapshot-loading');
  });

  it('renders the error banner on a fetch error', () => {
    holder.result = { kind: 'error', message: 'connection refused' };
    const html = render();
    expect(html).toContain('snapshot-error');
    expect(html).toContain('connection refused');
  });

  it('renders the empty banner when there is no recent snapshot', () => {
    holder.result = { kind: 'empty', reason: 'no_recent_row' };
    expect(render()).toContain('snapshot-empty');
  });

  it('renders all tabs, the default Market content, and a complete ARIA tabs pattern', () => {
    holder.result = { kind: 'present', envelope: fixtureEnvelope() };
    const html = render();
    expect(html).toContain('Morning brief');
    for (const label of ['Market', 'Equities', 'Risk', 'Actions']) {
      expect(html).toContain(label);
    }
    // Default tab is Market → its first NarrativeSection heading is present.
    expect(html).toContain('Market regime');
    // ARIA wiring: tablist + tab/panel association for the active tab.
    expect(html).toContain('role="tablist"');
    expect(html).toContain('aria-controls="morning-brief-panel-market"');
    expect(html).toContain('id="morning-brief-panel-market"');
    expect(html).toContain('aria-labelledby="morning-brief-tab-market"');
  });
});
