import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { FxTradeIdeaRow } from '@/lib/twelve-x/types';
import LevelFixSection from './LevelFixSection';

describe('LevelFixSection', () => {
  it('renders a loading state before the client-side fix fetch resolves', () => {
    const idea: FxTradeIdeaRow = {
      run_date: '2026-06-12',
      rank: 1,
      pair: 'EUR/USD',
      direction: 'long',
      title: 'EUR/USD long',
      thesis: '',
      catalyst: '',
      levels: [],
      citations: [],
      as_of: '2026-06-26T00:00:00Z',
    };
    const html = renderToStaticMarkup(createElement(LevelFixSection, { idea }));
    // Effects never run under static markup, so the fetch never resolves here.
    expect(html).toContain('data-testid="level-fix-loading"');
    expect(html).toContain('Loading fix series');
  });
});
