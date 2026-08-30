import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TickerDossierView from './TickerDossierView';

// Mock dependencies
vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('@/lib/hooks/use-async-data', () => ({
  useAsyncData: vi.fn(),
}));

vi.mock('@/lib/queries', () => ({
  fetchTickerDossier: vi.fn(),
}));

vi.mock('next/link', () => ({
  default: ({ children, href, className }: any) =>
    createElement('a', { href, className }, children),
}));

vi.mock('lucide-react', () => ({
  ArrowLeft: () => createElement('svg', { 'data-icon': 'arrow-left' }),
  ArrowUpRight: () => createElement('svg', { 'data-icon': 'arrow-up-right' }),
  TrendingUp: () => createElement('svg', { 'data-icon': 'trending-up' }),
  TrendingDown: () => createElement('svg', { 'data-icon': 'trending-down' }),
  Lock: () => createElement('svg', { 'data-icon': 'lock' }),
}));

vi.mock('@/components/portfolio/PortfolioSectionNav', () => ({
  default: () => createElement('nav', { 'data-testid': 'section-nav' }),
}));

vi.mock('@/components/page-skeleton', () => ({
  default: () => createElement('div', { 'data-testid': 'page-skeleton' }),
}));

vi.mock('@/components/shared/as-of-badge', () => ({
  AsOfBadge: ({ date }: any) => createElement('span', { 'data-testid': 'as-of-badge' }, date),
}));

vi.mock('@/components/shared/signed-conviction-badge', () => ({
  SignedConvictionBadge: ({ value }: any) =>
    createElement('span', { 'data-testid': 'conviction-badge', 'data-value': value }, `+${value}`),
}));

vi.mock('@/components/ui', () => ({
  Badge: ({ children, variant }: any) =>
    createElement('span', { 'data-testid': 'badge', 'data-variant': variant }, children),
  StatCard: () => createElement('div', { 'data-testid': 'stat-card' }),
  formatPct: (v: number | null) => (v != null ? `${v > 0 ? '+' : ''}${v.toFixed(2)}%` : '—'),
  pnlColor: (v: number | null) => (v != null ? (v >= 0 ? 'text-up' : 'text-down') : ''),
}));

vi.mock('@/components/portfolio/theses/ThesisProvenanceStrip', () => ({
  ThesisProvenanceStrip: () => createElement('div', { 'data-testid': 'provenance-strip' }),
}));

vi.mock('@/lib/holdings-decisions', () => ({
  decisionNodeFor: vi.fn(),
}));

vi.mock('./ConvictionHistory', () => ({
  default: () => createElement('div', { 'data-testid': 'analysis-history' }),
}));

import { useDashboard } from '@/lib/dashboard-context';
import { useAsyncData } from '@/lib/hooks/use-async-data';

describe('TickerDossierView — command band structure', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a full-width bordered command band, not a glass-card', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: {
        positions: [
          {
            ticker: 'XLE',
            name: 'Energy Select Sector SPDR',
            weight_actual: 17.2,
            weight_target: null,
            entry_price: 84.2,
            entry_date: '2026-01-15',
            since_entry_return_pct: 4.8,
            unrealized_pnl_pct: null,
          },
        ],
      },
      loading: false,
    } as any);

    vi.mocked(useAsyncData).mockReturnValue({
      data: {
        ticker: 'XLE',
        analyst: {
          ticker: 'XLE',
          stance: 'buy',
          conviction_score: 3,
          thesis: 'Energy scarcity',
          bull_case: '',
          bear_case: '',
          tailwinds: [],
          headwinds: [],
          risks: '',
          technicals: '',
          expectations: '',
          fundamentals: '',
          price_targets: null,
          sources: [],
        },
        analystDate: '2026-07-18',
        coverage: null,
        decisions: [],
      },
      loading: false,
      error: null,
    } as any);

    const html = renderToStaticMarkup(createElement(TickerDossierView, { ticker: 'XLE' }));

    expect(html).toContain('dossier-command');
    expect(html).toContain('data-testid="dossier-command-band"');
    expect(html).toContain('data-region="metrics"');
    expect(html).not.toMatch(/dossier-command[^>]*glass-card/);
    expect(html).toContain('border-');
  });

  it('renders held state with explicit "held" label', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: {
        positions: [
          {
            ticker: 'XLE',
            name: 'Energy Select Sector SPDR',
            weight_actual: 17.2,
            weight_target: null,
            entry_price: 84.2,
            entry_date: '2026-01-15',
            since_entry_return_pct: 4.8,
            unrealized_pnl_pct: null,
          },
        ],
      },
      loading: false,
    } as any);

    vi.mocked(useAsyncData).mockReturnValue({
      data: { ticker: 'XLE', analyst: null, analystDate: null, coverage: null, decisions: [] },
      loading: false,
      error: null,
    } as any);

    const html = renderToStaticMarkup(createElement(TickerDossierView, { ticker: 'XLE' }));

    expect(html).toContain('held');
    expect(html).toContain('17.20%'); // weight
    expect(html).toContain('+4.80%'); // since-entry formatted
  });

  it('Observer: locks weight/NAV metrics; no raw weight_actual', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: {
        positions: [
          {
            ticker: 'XLE',
            name: 'Energy Select Sector SPDR',
            weight_actual: 17.2,
            weight_target: null,
            entry_price: 84.2,
            entry_date: '2026-01-15',
            since_entry_return_pct: 4.8,
            unrealized_pnl_pct: null,
          },
        ],
        position_history: [
          { date: '2026-01-15', ticker: 'XLE', weight_pct: 4, category: 'energy', thesis_id: 'energy' },
          { date: '2026-07-18', ticker: 'XLE', weight_pct: 17.2, category: 'energy', thesis_id: 'energy' },
        ],
        position_events: [
          {
            date: '2026-01-15',
            ticker: 'XLE',
            event: 'OPEN',
            weight_pct: 4,
            prev_weight_pct: 0,
            weight_change_pct: 4,
            price: 84.2,
            thesis_id: 'energy',
            reason: 'Entered energy sleeve',
          },
          {
            date: '2026-07-18',
            ticker: 'XLE',
            event: 'ADD',
            weight_pct: 17.2,
            prev_weight_pct: 4,
            weight_change_pct: 13.2,
            price: 90,
            thesis_id: 'energy',
            reason: 'Added on confirmation',
          },
        ],
      },
      loading: false,
    } as any);

    vi.mocked(useAsyncData).mockReturnValue({
      data: { ticker: 'XLE', analyst: null, analystDate: null, coverage: null, decisions: [] },
      loading: false,
      error: null,
    } as any);

    const html = renderToStaticMarkup(
      createElement(TickerDossierView, { ticker: 'XLE', tier: 'free' }),
    );
    expect(html).toContain('locked-surface');
    expect(html).not.toContain('17.20%');
    expect(html).not.toContain('data-region="metrics"');
    // Position-history Allocation/Change must not leak historical house weights
    expect(html).toContain('data-region="position-history"');
    expect(html).not.toContain('>4.0%<');
    expect(html).not.toContain('>13.2pp<');
    expect(html).not.toContain('+13.2pp');
    expect(html).not.toMatch(/Allocation[\s\S]*?4\.0%/);
    // Book P&L (since-entry) also house_weights_nav
    expect(html).not.toContain('+4.80%');
  });

  it('renders covered-unheld state with explicit "covered · unheld" label', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: { positions: [] },
      loading: false,
    } as any);

    vi.mocked(useAsyncData).mockReturnValue({
      data: {
        ticker: 'COPX',
        analyst: {
          ticker: 'COPX',
          stance: 'buy',
          conviction_score: 3,
          thesis: 'Copper deficit',
          bull_case: '',
          bear_case: '',
          tailwinds: [],
          headwinds: [],
          risks: '',
          technicals: '',
          expectations: '',
          fundamentals: '',
          price_targets: null,
          sources: [],
        },
        analystDate: '2026-07-18',
        coverage: { current_recommendation_key: 'copx-analysis' },
        decisions: [],
      },
      loading: false,
      error: null,
    } as any);

    const html = renderToStaticMarkup(createElement(TickerDossierView, { ticker: 'COPX' }));

    expect(html).toMatch(/covered.*unheld/i);
    expect(html).toContain('Current view');
    expect(html).toContain('Latest source');
  });

  it('displays position metrics when held: weight, since-entry, entry', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: {
        positions: [
          {
            ticker: 'XLE',
            name: 'Energy Select Sector SPDR',
            weight_actual: 17.2,
            weight_target: 18.0,
            entry_price: 84.2,
            entry_date: '2026-01-15',
            since_entry_return_pct: 4.8,
            unrealized_pnl_pct: null,
          },
        ],
      },
      loading: false,
    } as any);

    vi.mocked(useAsyncData).mockReturnValue({
      data: { ticker: 'XLE', analyst: null, analystDate: null, coverage: null, decisions: [] },
      loading: false,
      error: null,
    } as any);

    const html = renderToStaticMarkup(createElement(TickerDossierView, { ticker: 'XLE' }));

    // Weight metric
    expect(html).toContain('17.20%');
    // Since-entry with P&L color
    expect(html).toContain('+4.80%');
    expect(html).toContain('text-up');
    // Entry price
    expect(html).toContain('$84.20');
  });

  it('includes as-of stamp in the command band', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: { positions: [] },
      loading: false,
    } as any);

    vi.mocked(useAsyncData).mockReturnValue({
      data: {
        ticker: 'XLE',
        analyst: null,
        analystDate: null,
        coverage: null,
        decisions: [{ run_date: '2026-07-18' }],
      },
      loading: false,
      error: null,
    } as any);

    const html = renderToStaticMarkup(createElement(TickerDossierView, { ticker: 'XLE' }));

    expect(html).toContain('2026-07-18');
    expect(html).toContain('latest analysis');
  });
});

describe('TickerDossierView — ticker lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('orders the page around view, position, outcome, and analysis provenance', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: {
        positions: [
          {
            ticker: 'XLE',
            name: 'Energy Select Sector SPDR',
            weight_actual: 5.2,
            weight_target: 6,
            entry_price: 84.2,
            entry_date: '2026-01-15',
            since_entry_return_pct: 4.8,
            unrealized_pnl_pct: null,
            rationale: 'Express persistent energy scarcity.',
            pm_notes: 'Hold while supply discipline persists.',
          },
        ],
        position_history: [
          { date: '2026-01-15', ticker: 'XLE', weight_pct: 4, category: 'energy', thesis_id: 'energy' },
          { date: '2026-07-18', ticker: 'XLE', weight_pct: 5.2, category: 'energy', thesis_id: 'energy' },
        ],
        position_events: [
          {
            date: '2026-01-15',
            ticker: 'XLE',
            event: 'OPEN',
            weight_pct: 4,
            prev_weight_pct: 0,
            weight_change_pct: 4,
            price: 84.2,
            thesis_id: 'energy',
            reason: 'Opened as the preferred energy expression.',
          },
          {
            date: '2026-07-18',
            ticker: 'XLE',
            event: 'ADD',
            weight_pct: 5.2,
            prev_weight_pct: 4,
            weight_change_pct: 1.2,
            price: 88.1,
            thesis_id: 'energy',
            reason: 'Derived from positions book vs prior committed book (digest unavailable).',
          },
        ],
      },
      loading: false,
    } as any);

    vi.mocked(useAsyncData).mockReturnValue({
      data: {
        ticker: 'XLE',
        analyst: {
          ticker: 'XLE',
          stance: 'buy',
          conviction_score: 3,
          thesis: 'Energy scarcity',
          bull_case: '',
          bear_case: '',
          tailwinds: [],
          headwinds: [],
          risks: '',
          technicals: '',
          expectations: '',
          fundamentals: '',
          price_targets: null,
          sources: [],
        },
        analystDate: '2026-07-18',
        coverage: { current_recommendation_key: 'analyst/XLE' },
        decisions: [
          {
            id: 'decision-1',
            run_date: '2026-07-18',
            stance: 'buy',
            conviction: 3,
            status: 'resolved',
            alpha: 0.02,
          },
        ],
        latestAttribution: {
          id: 'attribution-1',
          date: '2026-07-18',
          ticker: 'XLE',
          sector_bucket: 'energy',
          weight_pct: 5.2,
          position_return_pct: 2.5,
          benchmark_return_pct: 1.7,
          contribution_pct: 0.13,
          selection_effect_pct: 0.04,
          allocation_effect_pct: 0,
          total_attribution_pct: 0.04,
          metrics_as_of: '2026-07-18',
          created_at: null,
        },
      },
      loading: false,
      error: null,
    } as any);

    const html = renderToStaticMarkup(createElement(TickerDossierView, { ticker: 'XLE' }));

    expect(html).toContain('Current view');
    expect(html).toContain('Portfolio position');
    expect(html).toContain('Position history');
    expect(html).toContain('Measured outcome');
    expect(html).toContain('Latest current-book lookback (diagnostic)');
    expect(html).toContain('analysis-history');
    expect(html).toContain('Energy scarcity');
    expect(html).toContain('Express persistent energy scarcity.');
    expect(html).toContain('Opened as the preferred energy expression.');
    expect(html).toContain('Observed from the committed position history.');
    expect(html).not.toContain('digest unavailable');
    expect(html).toContain('Current leg');
    expect(html).toContain('2.50%');
    expect(html).toContain('0.13%');
    expect(html).toContain('0.04%');
    expect(html).toContain(
      '/pipeline?date=2026-07-18&amp;stage=selection'
    );
    expect(html).toContain('Open latest analysis');
    expect(html).not.toContain('Research argument');
    expect(html).not.toContain('Dossier state');
  });

  it('keeps a previously held ticker useful after exit', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: {
        positions: [],
        position_history: [
          { date: '2026-01-01', ticker: 'XLE', weight_pct: 5, category: 'energy', thesis_id: 'energy' },
          { date: '2026-06-01', ticker: 'XLE', weight_pct: 0, category: 'energy', thesis_id: 'energy' },
        ],
        position_events: [
          {
            date: '2026-06-01',
            ticker: 'XLE',
            event: 'EXIT',
            weight_pct: 0,
            prev_weight_pct: 5,
            weight_change_pct: -5,
            price: 90,
            thesis_id: 'energy',
            reason: 'The catalyst was fully priced.',
          },
        ],
      },
      loading: false,
    } as any);

    vi.mocked(useAsyncData).mockReturnValue({
      data: {
        ticker: 'XLE',
        analyst: null,
        analystDate: null,
        coverage: null,
        decisions: [
          { id: 'd1', run_date: '2026-01-01', conviction: 3, status: 'resolved' },
        ],
        latestAttribution: null,
      },
      loading: false,
      error: null,
    } as any);

    const html = renderToStaticMarkup(createElement(TickerDossierView, { ticker: 'XLE' }));

    expect(html).toContain('Previously held');
    expect(html).toContain('2026-01-01–2026-06-01');
    expect(html).toContain('The catalyst was fully priced.');
    expect(html).toContain('No current position');
  });
});
