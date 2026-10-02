import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { HOLDINGS_COLUMN_ORDER, HOLDINGS_MIN_WIDTH } from '@/lib/desk/column-priority';
import { DeskTable, type DeskTableColumn } from './DeskTable';

const COLUMNS: DeskTableColumn[] = HOLDINGS_COLUMN_ORDER.map((id) => ({
  id,
  label: id,
  kind: id === 'Weight' ? 'weight' : 'text',
}));

const ROW = {
  id: 'dbo',
  cells: {
    Ticker: 'DBO',
    Name: 'Oil',
    Weight: 5.1,
    Day: null,
    Mark: null,
    Value: null,
    Shares: null,
    Thesis: 'T-1',
    Source: 'book',
  },
};

function htmlFor(width: number) {
  return renderToStaticMarkup(
    createElement(DeskTable, {
      columns: COLUMNS,
      width,
      groups: [{ id: 'energy', label: 'Energy', rows: [ROW] }],
    }),
  );
}

describe('DeskTable', () => {
  it('drops holdings columns in priority order as width shrinks', () => {
    const wide = htmlFor(HOLDINGS_MIN_WIDTH.Source);
    expect(wide).toContain('data-column="Source"');
    expect(wide).toContain('data-column="Name"');
    expect(wide).toContain('Energy');

    const noSource = htmlFor(HOLDINGS_MIN_WIDTH.Source - 1);
    expect(noSource).not.toContain('data-column="Source"');
    expect(noSource).toContain('data-column="Thesis"');

    const narrow = htmlFor(HOLDINGS_MIN_WIDTH.Name - 1);
    expect(narrow).toContain('data-column="Ticker"');
    expect(narrow).toContain('data-column="Weight"');
    expect(narrow).toContain('data-column="Day"');
    expect(narrow).toContain('data-column="Mark"');
    expect(narrow).not.toContain('data-column="Name"');
    expect(narrow).not.toContain('data-column="Value"');
    expect(narrow).not.toContain('data-column="Shares"');
    expect(narrow).not.toContain('data-column="Thesis"');
    expect(narrow).not.toContain('data-column="Source"');
    expect(narrow).toContain('>—<');
  });

  it('renders empty and error frames', () => {
    const empty = renderToStaticMarkup(createElement(DeskTable, { columns: COLUMNS, rows: [] }));
    const error = renderToStaticMarkup(
      createElement(DeskTable, { columns: COLUMNS, rows: [ROW], state: 'error', errorMessage: 'upstream empty' }),
    );
    expect(empty).toContain('data-testid="desk-state-empty"');
    expect(error).toContain('upstream empty');
    expect(error).not.toContain('data-testid="desk-table-row"');
  });
});
