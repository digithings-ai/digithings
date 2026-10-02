import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DeskFeed } from './DeskFeed';

describe('DeskFeed', () => {
  it('renders tape rows and an empty frame when there are none', () => {
    const tape = renderToStaticMarkup(
      createElement(DeskFeed, {
        items: [{ id: '1', time: '09:31', title: 'SPY', detail: 'mark 610' }],
      }),
    );
    const empty = renderToStaticMarkup(createElement(DeskFeed, { items: [] }));
    const error = renderToStaticMarkup(
      createElement(DeskFeed, { items: [], state: 'error', errorMessage: 'tape unavailable' }),
    );
    expect(tape).toContain('data-testid="desk-feed"');
    expect(tape).toContain('SPY');
    expect(empty).toContain('No tape');
    expect(error).toContain('tape unavailable');
    expect(error).not.toContain('lorem');
  });
});
