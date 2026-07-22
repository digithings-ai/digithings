import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { TheReadBody } from './the-read';
import type { DigestPayload } from '@/lib/snapshot-types';

function digest(overrides: Partial<DigestPayload> = {}): DigestPayload {
  return {
    segment: 'master-digest',
    date: '2026-06-22',
    bias: 'bullish',
    headline: 'Equities hold a bullish bid despite rotation into bonds.',
    material_findings: [],
    sources: [],
    notes: '',
    market_regime_snapshot: 'Risk-on with broadening participation across sectors.',
    alt_data_dashboard: 'Card spend steady week over week.',
    institutional_summary: 'Net institutional inflows into large-cap tech.',
    asset_classes_summary: 'Bonds bid; gold firm.',
    us_equities_summary: 'Breadth improving beyond mega-cap.',
    thesis_tracker: 'AI capex thesis intact.',
    portfolio_recommendations: 'Trim semis into strength.',
    actionable_summary: [{ priority: 1, label: 'Trim NVDA', rationale: 'Valuation stretched into earnings.' }],
    risk_radar: [{ horizon_hours: 48, label: 'CPI print', trigger: 'Hot core CPI Thursday.' }],
    segment_freshness: { 'us-equities': { source: 'today', as_of: '2026-06-22' } },
    ...overrides,
  };
}

describe('TheReadBody', () => {
  it('leads with the regime, actionable, and risk radar', () => {
    const html = renderToStaticMarkup(createElement(TheReadBody, { digest: digest() }));
    expect(html).toContain('Market regime');
    expect(html).toContain('Risk-on with broadening participation');
    expect(html).toContain('Trim NVDA'); // actionable
    expect(html).toContain('CPI print'); // risk radar
    // regime/actionable lead must appear before the collapsed deep sections
    expect(html.indexOf('Risk-on with broadening')).toBeLessThan(html.indexOf('US equities'));
  });

  it('renders per-segment freshness badges', () => {
    const html = renderToStaticMarkup(createElement(TheReadBody, { digest: digest() }));
    expect(html).toContain('read-freshness');
    expect(html).toContain('us-equities');
    expect(html).toContain('today');
  });

  it('collapses the deeper segments into details elements', () => {
    const html = renderToStaticMarkup(createElement(TheReadBody, { digest: digest() }));
    expect(html).toContain('<details');
    expect(html).toContain('Institutional flows');
    expect(html).toContain('Thesis tracker');
  });

  it('renders the research read as a flat hairline workspace', () => {
    const html = renderToStaticMarkup(createElement(TheReadBody, { digest: digest() }));
    expect(html).toContain('data-testid="why-read-workspace"');
    expect(html).toContain('data-testid="why-read-disclosures"');
    expect(html).not.toContain('glass-card');
  });
});
