import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import BrokerProfilePanel from './BrokerProfilePanel';
import type { MatrixCell } from '@/lib/twelve-x/types';

function cell(partial: Partial<MatrixCell> & { broker: string; column: MatrixCell['column'] }): MatrixCell {
  return {
    currency: partial.column,
    direction: 'bullish',
    conviction: 'high',
    run_date: '2026-06-24',
    report_date: null,
    source_file: `${partial.broker}-${partial.column}.md`,
    ...partial,
  };
}

const CELLS: MatrixCell[] = [
  cell({ broker: 'Atlas Macro', column: 'USD', direction: 'bullish', conviction: 'high', currency: 'USD', rationale: 'Dollar smile intact', key_facts: ['Real yields rising'], targets: [{ label: 'TP', level: 1.05 }], signal: 'Add on dips' }),
  cell({ broker: 'Atlas Macro', column: 'EUR', direction: 'bearish', conviction: 'medium', currency: 'EUR/USD', source_file: 'atlas-eur.md', run_date: '2026-06-23' }),
  cell({ broker: 'Meridian FX', column: 'JPY', direction: 'watch', conviction: 'low', currency: 'JPY' }),
];

function render(broker: string | null) {
  return renderToStaticMarkup(
    createElement(BrokerProfilePanel, {
      broker,
      cells: CELLS,
      onClose: () => {},
      onOpenBrief: () => {},
    }),
  );
}

describe('BrokerProfilePanel', () => {
  it('renders nothing when no broker is selected', () => {
    expect(render(null)).toBe('');
  });

  it('renders only the focused broker’s views (a slide-over dialog)', () => {
    const html = render('Atlas Macro');
    expect(html).toContain('role="dialog"');
    expect(html).toContain('Atlas Macro');
    // Atlas's two instruments show; Meridian's JPY view must NOT leak in.
    expect(html).toContain('USD');
    expect(html).toContain('EUR/USD');
    expect(html).not.toContain('Meridian FX');
  });

  it('shows the desk’s rationale, key facts, signal and target levels', () => {
    const html = render('Atlas Macro');
    expect(html).toContain('Dollar smile intact');
    expect(html).toContain('Real yields rising');
    expect(html).toContain('Add on dips');
    expect(html).toContain('TP 1.05');
  });

  it('tallies the net tilt across the desk’s views (1 bull / 1 bear here)', () => {
    const html = render('Atlas Macro');
    expect(html).toContain('2 views');
    expect(html).toContain('1 bull');
    expect(html).toContain('1 bear');
  });

  it('offers an open-brief affordance per view', () => {
    const html = render('Atlas Macro');
    expect(html).toContain('Open brief');
  });

  it('handles a broker with no views gracefully', () => {
    const html = render('Nonexistent Desk');
    expect(html).toContain('No standing views from this desk');
  });
});
