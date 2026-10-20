import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DeskState } from './DeskState';

describe('DeskState', () => {
  it('renders loading, empty, and error without a zero placeholder', () => {
    const loading = renderToStaticMarkup(createElement(DeskState, { state: 'loading' }));
    const empty = renderToStaticMarkup(
      createElement(DeskState, { state: 'empty', emptyMessage: 'No book yet' }),
    );
    const error = renderToStaticMarkup(
      createElement(DeskState, { state: 'error', errorMessage: 'upstream empty' }),
    );
    const ready = renderToStaticMarkup(
      createElement(DeskState, { state: 'ready' }, createElement('span', null, 'ready-body')),
    );

    expect(loading).toContain('data-testid="desk-state-loading"');
    expect(loading).toContain('Loading');
    expect(empty).toContain('data-testid="desk-state-empty"');
    expect(empty).toContain('No book yet');
    expect(error).toContain('data-testid="desk-state-error"');
    expect(error).toContain('upstream empty');
    expect(ready).toContain('ready-body');
    expect(ready).not.toContain('desk-state-loading');
    expect(`${loading}${empty}${error}`).not.toContain('>0<');
  });
});
