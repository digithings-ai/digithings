import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import MatrixTab from './MatrixTab';
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
  cell({ broker: 'Atlas Macro', column: 'USD', rationale: 'Dollar smile intact' }),
  cell({ broker: 'Meridian FX', column: 'JPY', direction: 'bearish', currency: 'JPY' }),
];

function render(initialSelectedBroker: string | null = null) {
  return renderToStaticMarkup(
    createElement(MatrixTab, { cells: CELLS, onOpenBrief: () => {}, initialSelectedBroker }),
  );
}

describe('MatrixTab', () => {
  it('renders the desk grid with a row per broker', () => {
    const html = render();
    expect(html).toContain('Desk view matrix');
    expect(html).toContain('Atlas Macro');
    expect(html).toContain('Meridian FX');
  });

  it('makes each broker label a button that opens its profile', () => {
    const html = render();
    // The desk label is an interactive button (the drill-in affordance), and the
    // copy advertises it.
    expect(html).toMatch(/<button[^>]*>\s*<span class="truncate">Atlas Macro<\/span>/);
    expect(html).toContain('desk name to see that broker');
  });

  it('does not open the broker profile by default', () => {
    const html = render();
    expect(html).not.toContain('role="dialog"');
  });

  it('opens the broker-profile slide-over when a broker is pre-selected', () => {
    const html = render('Atlas Macro');
    expect(html).toContain('role="dialog"');
    expect(html).toContain('Dollar smile intact'); // Atlas's view detail
    expect(html).toContain('1 view');
  });
});
