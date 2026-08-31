import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import MatrixCellHistoryPanel, { MatrixCellHistoryPanelBody } from './MatrixCellHistoryPanel';
import type { MatrixCell, MatrixCellHistoryEntry } from '@/lib/twelve-x/types';

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

const history: MatrixCellHistoryEntry[] = [
  {
    run_date: '2026-06-23',
    report_date: '2026-06-23',
    source_file: 'atlas-2026-06-23.pdf',
    direction: 'bullish',
    conviction: 'medium',
    rationale: 'Previous view',
  },
  {
    run_date: '2026-06-22',
    report_date: '2026-06-22',
    source_file: 'atlas-2026-06-22.pdf',
    direction: 'neutral',
    conviction: 'low',
    rationale: 'Oldest view',
  },
];

function renderPanel(cellData: MatrixCell | null) {
  return renderToStaticMarkup(
    createElement(MatrixCellHistoryPanel, {
      cell: cellData,
      onClose: () => {},
      onOpenBrief: () => {},
    }),
  );
}

function renderBody(cellData: MatrixCell) {
  return renderToStaticMarkup(
    createElement(MatrixCellHistoryPanelBody, {
      cell: cellData,
      onClose: () => {},
      onOpenBrief: () => {},
    }),
  );
}

describe('MatrixCellHistoryPanel', () => {
  it('renders nothing when cell is null (closed)', () => {
    expect(renderPanel(null)).toBe('');
  });

  it('renders the primary view and history entries', () => {
    const cellData = cell({
      broker: 'Atlas Macro',
      column: 'USD',
      currency: 'USD',
      run_date: '2026-06-24',
      rationale: 'Latest view',
      history,
    });
    const html = renderBody(cellData);
    expect(html).toContain('Atlas Macro');
    expect(html).toContain('USD');
    expect(html).toContain('Latest view'); // primary
    expect(html).toContain('Previous view'); // history[0]
    expect(html).toContain('Oldest view'); // history[1]
  });

  it('shows each view with its date and an open-brief affordance', () => {
    const cellData = cell({
      broker: 'Atlas Macro',
      column: 'USD',
      history,
    });
    const html = renderBody(cellData);
    expect(html).toContain('2026-06-24'); // primary date
    expect(html).toContain('2026-06-23'); // history[0] date
    expect(html).toContain('2026-06-22'); // history[1] date
    // Each view should have an open-brief button
    const openBriefCount = (html.match(/Open brief/g) || []).length;
    expect(openBriefCount).toBe(3); // primary + 2 history entries
  });

  it('indicates the count in the header when there are history entries', () => {
    const cellData = cell({
      broker: 'Atlas Macro',
      column: 'USD',
      history,
    });
    const html = renderBody(cellData);
    expect(html).toContain('3 views'); // 1 primary + 2 history
  });
});
