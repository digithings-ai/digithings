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
  TrendingUp: () => createElement('svg', { 'data-icon': 'trending-up' }),
  TrendingDown: () => createElement('svg', { 'data-icon': 'trending-down' }),
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

vi.mock('./AnalystDossierCard', () => ({
  default: () => createElement('div', { 'data-testid': 'analyst-dossier-card' }),
}));

vi.mock('./ConvictionHistory', () => ({
  default: () => createElement('div', { 'data-testid': 'conviction-history' }),
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
    expect(html).toContain('coverage');
    expect(html).toContain('analyst');
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
    expect(html).toContain('as of');
  });
});

describe('TickerDossierView — editorial analyst workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders AnalystDossierCard when analyst payload exists', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: { positions: [] },
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

    expect(html).toContain('analyst-dossier-card');
    expect(html).toContain('data-region="analyst-workspace"');
    expect(html).toContain('data-region="dossier-context"');
  });

  it('renders ConvictionHistory below the analyst workspace', () => {
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
        decisions: [
          { id: 'd1', run_date: '2026-01-01', conviction: 3, status: 'resolved' },
        ],
      },
      loading: false,
      error: null,
    } as any);

    const html = renderToStaticMarkup(createElement(TickerDossierView, { ticker: 'XLE' }));

    expect(html).toContain('conviction-history');
  });
});
