import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/components/ui', () => ({
  Badge: (p: { children?: unknown; className?: string }) =>
    createElement('span', { 'data-badge': true, className: p.className }, p.children as never),
}));

import { AsOfBadge } from './as-of-badge';

const now = new Date('2026-06-24T16:00:00Z');

describe('AsOfBadge (F7 canonical)', () => {
  it('renders nothing without a date', () => {
    expect(renderToStaticMarkup(createElement(AsOfBadge, { date: null, now }))).toBe('');
  });
  it('shows a fresh inline pill for a same/prev-day date (date-only path)', () => {
    const html = renderToStaticMarkup(createElement(AsOfBadge, { date: '2026-06-23', now }));
    expect(html).toContain('as of Jun 23');
    expect(html).not.toContain('stale');
  });
  it('treats today as fresh on the date-only path', () => {
    expect(
      renderToStaticMarkup(createElement(AsOfBadge, { date: '2026-06-24', now }))
    ).not.toContain('stale');
  });
  it('marks dates older than yesterday as stale on the date-only path', () => {
    const html = renderToStaticMarkup(createElement(AsOfBadge, { date: '2026-06-20', now }));
    expect(html).toContain('stale');
    expect(html).toContain('as of Jun 20');
  });
  it('marks stale + shows formatAge when a createdAt > threshold is given', () => {
    const html = renderToStaticMarkup(
      createElement(AsOfBadge, { date: '2026-06-20', createdAt: '2026-06-20T16:00:00Z', now })
    );
    expect(html).toContain('stale');
    expect(html).toContain('4d ago');
  });
});
