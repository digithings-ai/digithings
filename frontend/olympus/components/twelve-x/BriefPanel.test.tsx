import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { FxBriefRow } from '@/lib/twelve-x/types';

/**
 * SSR-only test (node env, renderToStaticMarkup — no jsdom/RTL). BriefPanel
 * loads its brief asynchronously via `getBrief` inside a `useEffect`, so under
 * static SSR the brief never lands in state on its own. We seed the loaded-brief
 * render path two ways:
 *   - mock `getBrief` so the import resolves without touching Supabase, and
 *   - mock React's `useState` so the FIRST `useState(null)` call (the `brief`
 *     state) initialises to our fixture, while every later `useState` keeps its
 *     real default. `useEffect` is stubbed to a no-op so the async loader and
 *     scroll-lock effects don't run during SSR.
 * This renders the same loaded markup a hydrated panel would show, letting us
 * assert how `central_thesis` is rendered.
 */
const fixtureBrief: FxBriefRow = {
  run_date: '2026-06-24',
  source_file: 'atlas-macro-2026-06-24.pdf',
  source_url: null,
  document_title: 'Atlas Macro Daily',
  broker_name: 'Atlas Macro',
  analyst_names: null,
  report_date: '2026-06-24',
  trader_relevance: 'high',
  central_thesis: '**Bold** thesis on the dollar.',
  brief_markdown: 'Body paragraph with _emphasis_.',
  currency_views: [],
  risk_events: [],
  macro_themes: [],
  positioning_signals: [],
};

vi.mock('@/lib/twelve-x/fetch', () => ({
  getBrief: vi.fn(async () => fixtureBrief),
}));

// Per-render control: `render()` resets `seeded` so the FIRST useState(null)
// call (the `brief` state) of each render is seeded with the fixture. The
// second null-initialised state (`error`) must keep its real null default, so
// we only seed once per render.
const seedControl = { seeded: false };

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react');
  const useState = ((initial: unknown) => {
    if (!seedControl.seeded && initial === null) {
      seedControl.seeded = true;
      return actual.useState(fixtureBrief as unknown);
    }
    return actual.useState(initial);
  }) as typeof actual.useState;
  return {
    ...actual,
    default: actual,
    useState,
    // No-op effects: the async loader / Escape / scroll-lock effects must not
    // run under SSR. The `brief` state is already seeded above.
    useEffect: () => {},
  };
});

import BriefPanel from './BriefPanel';

afterEach(() => {
  vi.clearAllMocks();
});

function render(over: Partial<FxBriefRow> = {}): string {
  Object.assign(fixtureBrief, over);
  seedControl.seeded = false;
  return renderToStaticMarkup(
    createElement(BriefPanel, {
      open: true,
      sourceFile: fixtureBrief.source_file,
      runDate: fixtureBrief.run_date,
      onClose: () => {},
    })
  );
}

describe('BriefPanel — central thesis markdown', () => {
  it('renders central_thesis through the markdown renderer (bold becomes <strong>)', () => {
    const html = render({ central_thesis: '**Bold** thesis on the dollar.' });
    // The thesis label still anchors the section.
    expect(html).toContain('Central thesis');
    // Markdown is rendered: the bold span becomes a <strong>, not literal asterisks.
    expect(html).toContain('<strong>Bold</strong>');
    expect(html).not.toContain('**Bold**');
  });

  it('omits the central-thesis section when there is no thesis', () => {
    const html = render({ central_thesis: null });
    expect(html).not.toContain('Central thesis');
  });

  it('still renders the markdown body independently of the thesis', () => {
    const html = render({
      central_thesis: '**Bold** thesis on the dollar.',
      brief_markdown: 'Body paragraph with _emphasis_.',
    });
    expect(html).toContain('<em>emphasis</em>');
  });
});
