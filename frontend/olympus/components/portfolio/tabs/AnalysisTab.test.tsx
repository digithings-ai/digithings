import { createElement } from 'react';
import type { ComponentProps, ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import AnalysisTab from './AnalysisTab';
import { useDashboard } from '@/lib/dashboard-context';
import type { Doc } from '@/lib/types';
import type { LibraryDocumentResult } from '@/lib/queries';

vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: vi.fn(),
}));

const useDashboardMock = vi.mocked(useDashboard);

function render(node: ReactElement): string {
  return renderToStaticMarkup(node);
}

function doc(overrides: Partial<Doc>): Doc {
  return {
    id: 'doc-1',
    date: '2026-06-18',
    title: 'PM memo',
    type: null,
    phase: 7,
    category: null,
    segment: null,
    sector: null,
    runType: 'delta',
    path: 'portfolio/pm-memo.md',
    ...overrides,
  };
}

function defaultProps(overrides: Partial<ComponentProps<typeof AnalysisTab>> = {}) {
  return {
    historyTimelineDates: ['2026-06-18', '2026-06-17'],
    portfolioHistoryRunKindByDate: new Map(),
    effHistoryDate: '2026-06-18',
    onSelectHistoryDate: vi.fn(),
    historyLatestDate: '2026-06-18',
    onClearHistoryDate: vi.fn(),
    portfolioDocDates: new Set<string>(),
    positionHistoryDates: new Set<string>(),
    pmDocsForHistory: [],
    pmActiveFile: null,
    pmLibraryDoc: null,
    pmLoading: false,
    onOpenPmDocument: vi.fn(),
    onClosePmDocument: vi.fn(),
    ...overrides,
  };
}

describe('AnalysisTab pipeline artifacts', () => {
  it('renders latest artifact date, source-of-truth summary, and cleaned memo prose', () => {
    useDashboardMock.mockReturnValue({
      loading: false,
      error: null,
      data: {
        pipeline_observability: {
          snapshot_date: '2026-06-18',
          market_thesis_exploration: null,
          thesis_vehicle_map: null,
          pm_allocation_memo: null,
          deliberation_session_index: null,
          deliberation_transcripts: [],
          asset_recommendations: [],
          risk_debate: null,
          pm_rebalance: {
            notes: 'Narrative from query_data may lag structured weights.',
            actions: [
              {
                ticker: 'NVDA',
                action: 'TRIM',
                current_pct: 35,
                target_pct: 25,
                rationale: 'get_market_data shows concentration risk.',
              },
            ],
            recommended_portfolio: [
              { ticker: 'NVDA', target_pct: 25 },
              { ticker: 'MSFT', weight_pct: 60 },
            ],
          },
        },
      },
    } as never);

    const html = render(createElement(AnalysisTab, defaultProps()));

    expect(html).toContain('Latest pipeline artifacts');
    expect(html).toContain('Snapshot 2026-06-18');
    expect(html).toContain('Post-risk-sizing book summary');
    expect(html).toContain('85.00%');
    expect(html).toContain('15.00%');
    expect(html).toContain('Narrative / memo notes');
    expect(html).toContain('source of truth');
    expect(html).toContain('data query');
    expect(html).toContain('market data lookup');
    expect(html).not.toContain('query_data');
    expect(html).not.toContain('get_market_data');
  });

  it('warns when selected PM memo docs are date-scoped but top artifacts are latest', () => {
    useDashboardMock.mockReturnValue({
      loading: false,
      error: null,
      data: {
        pipeline_observability: {
          snapshot_date: '2026-06-18',
          market_thesis_exploration: null,
          thesis_vehicle_map: null,
          pm_allocation_memo: null,
          deliberation_session_index: null,
          deliberation_transcripts: [],
          asset_recommendations: [],
          risk_debate: null,
          pm_rebalance: {
            notes: '',
            actions: [{ ticker: 'NVDA', action: 'HOLD', current_pct: 20, target_pct: 20 }],
            recommended_portfolio: [{ ticker: 'NVDA', target_pct: 20 }],
          },
        },
      },
    } as never);

    const html = render(
      createElement(
        AnalysisTab,
        defaultProps({
          effHistoryDate: '2026-06-17',
        })
      )
    );

    expect(html).toContain('PM memo documents below are scoped to 2026-06-17');
    expect(html).toContain('latest pipeline snapshot from 2026-06-18');
  });
});

describe('AnalysisTab PM memo expansion', () => {
  it('marks active rows expanded and renders the inline document below the row', () => {
    useDashboardMock.mockReturnValue({ loading: false, error: null, data: null });
    const activeDoc = doc({ id: 'active-doc', path: 'portfolio/recommendations.md' });
    const inactiveDoc = doc({ id: 'inactive-doc', path: 'portfolio/deliberations.md' });
    const libraryDoc: LibraryDocumentResult = {
      id: activeDoc.id,
      date: activeDoc.date,
      document_key: 'recommendations',
      view: 'markdown',
      markdown: '# PM memo — 2026-06-18\n\nExpanded memo body.',
      payload: null,
    };

    const html = render(
      createElement(
        AnalysisTab,
        defaultProps({
          pmDocsForHistory: [activeDoc, inactiveDoc],
          pmActiveFile: activeDoc,
          pmLibraryDoc: libraryDoc,
        })
      )
    );

    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('aria-controls="pm-doc-active-doc"');
    expect(html).toContain('Hide');
    expect(html).toContain('Open');
    expect(html).toContain('pm-doc-active-doc');
    expect(html).toContain('Expanded memo body.');
  });
});
