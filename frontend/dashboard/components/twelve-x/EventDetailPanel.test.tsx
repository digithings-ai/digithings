import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import EventDetailPanel from './EventDetailPanel';
import type { MatchedOpinions } from './EventsTab';
import type { FxEconomicCalendarRow } from '@/lib/twelve-x/types';

function row(
  partial: Partial<FxEconomicCalendarRow> & { event_date: string },
): FxEconomicCalendarRow {
  return {
    id: Math.floor(Math.random() * 1e9),
    external_id: 'x',
    event_time: null,
    country: 'US',
    event_name: 'Some event',
    category: 'macro',
    impact: 'medium',
    actual: null,
    forecast: null,
    prior: null,
    event_datetime_utc: null,
    ...partial,
  };
}

const event: FxEconomicCalendarRow = row({
  id: 1,
  event_date: '2026-06-22',
  event_time: '12:30',
  country: 'US',
  event_name: 'Core PCE Price Index',
  impact: 'high',
  prior: '2.7%',
  forecast: '2.6%',
  actual: '2.5%',
  event_datetime_utc: '2026-06-22T12:30:00Z',
});

const opinions: MatchedOpinions = {
  mentions: 3,
  brokers: ['Goldman', 'JPM'],
  citations: [
    {
      broker: 'Goldman',
      expected_outcome: 'In line with consensus',
      fx_impact: 'USD bid on a beat',
      source_file: 'gs-2026.pdf',
      brief_key: 'gs',
    },
  ],
  eventKey: 'core-pce',
  runDate: '2026-06-22',
};

function render(props: Parameters<typeof EventDetailPanel>[0]): string {
  return renderToStaticMarkup(createElement(EventDetailPanel, props));
}

describe('EventDetailPanel', () => {
  it('renders nothing when event is null (closed)', () => {
    const html = render({ event: null, opinions: null, onClose: () => {} });
    expect(html).toBe('');
  });

  it('renders the event title, country and a high RISK level', () => {
    const html = render({ event, opinions, onClose: () => {} });
    expect(html).toContain('Core PCE Price Index');
    expect(html).toContain('US');
    // High-impact event is flagged as a high risk level with the warn token —
    // severity is not P&L, so it must not wear --down (#1538 F5 re-toning).
    expect(html).toContain('text-warn');
    expect(html).not.toContain('text-down');
    expect(html.toLowerCase()).toContain('high');
  });

  it('renders the Prior / Forecast / Actual row', () => {
    const html = render({ event, opinions, onClose: () => {} });
    expect(html).toMatch(/Prior[\s\S]{0,80}2\.7%/);
    expect(html).toMatch(/Forecast[\s\S]{0,80}2\.6%/);
    expect(html).toMatch(/Actual[\s\S]{0,80}2\.5%/);
  });

  it('renders the broker opinions: mentions, broker names and citation detail', () => {
    const html = render({ event, opinions, onClose: () => {} });
    // mentions count surfaces
    expect(html).toContain('3');
    // broker name + its expectation/fx-impact commentary
    expect(html).toContain('Goldman');
    expect(html).toContain('In line with consensus');
    expect(html).toContain('USD bid on a beat');
  });

  it('shows a graceful empty state when there is no desk commentary', () => {
    const html = render({ event, opinions: null, onClose: () => {} });
    expect(html).toContain('No desk commentary for this event yet.');
  });

  it('renders as a slide-over dialog (role=dialog, aria-modal)', () => {
    const html = render({ event, opinions, onClose: () => {} });
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
  });
});
