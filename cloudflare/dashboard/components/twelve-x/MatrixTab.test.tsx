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
  cell({ broker: 'research Macro', column: 'USD', rationale: 'Dollar smile intact' }),
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
    expect(html).toContain('research Macro');
    expect(html).toContain('Meridian FX');
  });

  it('makes each broker label a button that opens its profile', () => {
    const html = render();
    // The desk label is an interactive button (the drill-in affordance), and the
    // copy advertises it.
    expect(html).toMatch(/<button[^>]*>\s*<span class="truncate">research Macro<\/span>/);
    expect(html).toContain('desk name to see that broker');
  });

  it('does not open the broker profile by default', () => {
    const html = render();
    expect(html).not.toContain('role="dialog"');
  });

  it('mounts the broker-profile slide-over shell when a broker is pre-selected', () => {
    const html = render('research Macro');
    // Wave-2: the panel chrome is the shared Sheet (Base UI Dialog) whose
    // popup lives in a client-only portal — static SSR never paints
    // role="dialog". The open-state content is pinned by
    // BrokerProfilePanel.test.tsx (BrokerProfileBody) and verified live (CDP).
    expect(html).not.toContain('aria-modal="true"');
  });
});
