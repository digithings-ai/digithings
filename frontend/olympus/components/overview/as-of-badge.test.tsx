import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AsOfBadge } from './as-of-badge';

const NOW = new Date('2026-06-13T12:00:00Z');

function render(date: string | null): string {
  return renderToStaticMarkup(createElement(AsOfBadge, { date, now: NOW }));
}

describe('AsOfBadge', () => {
  it('renders nothing without a date', () => {
    expect(render(null)).toBe('');
  });

  it('shows a fresh "as of" pill for today (no stale marker)', () => {
    const html = render('2026-06-13');
    expect(html).toContain('as of Jun 13');
    expect(html).not.toContain('stale');
  });

  it('treats yesterday as still fresh', () => {
    expect(render('2026-06-12')).not.toContain('stale');
  });

  it('marks dates older than yesterday as stale', () => {
    const html = render('2026-06-09');
    expect(html).toContain('stale');
    expect(html).toContain('as of Jun 9');
  });
});
