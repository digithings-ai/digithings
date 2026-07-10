import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import type { FxBriefRow } from '@/lib/twelve-x/types';

/**
 * SSR-only test (node env, renderToStaticMarkup — no jsdom/RTL). Since the
 * panel chrome moved onto the shared @digithings/web Sheet (#1450), the popup
 * lives in a Base UI portal that never renders under static SSR — so these
 * content assertions target the exported BriefPanelBody (the local data/content
 * half of the panel) directly, with the loaded-brief state passed as props.
 * This is the same loaded markup a hydrated panel shows inside the sheet.
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

// The module under test imports the Supabase-backed fetchers; mock them so the
// import never touches a client (the panel's fetch effect is not under test).
vi.mock('@/lib/twelve-x/fetch', () => ({
  getBrief: vi.fn(async () => fixtureBrief),
}));

import { BriefPanelBody } from './BriefPanel';

function render(over: Partial<FxBriefRow> = {}): string {
  return renderToStaticMarkup(
    createElement(BriefPanelBody, {
      brief: { ...fixtureBrief, ...over },
      loading: false,
      error: null,
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
