import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import DigestBrief from './DigestBrief';

/**
 * SSR-only test (node env, renderToStaticMarkup — no jsdom/RTL). DigestBrief is
 * pure props → markup, so static SSR renders exactly what a hydrated card shows.
 * Pins the #1450 adoption contract: the summary renders through SafeMarkdown
 * inside the canonical .chat-md typography scope, with `whitespace-pre-line`
 * kept so plain-text summaries keep their exact line layout (react-markdown
 * emits soft breaks as literal "\n" text nodes).
 */

type Digest = Parameters<typeof DigestBrief>[0]['digest'];

const baseDigest: NonNullable<Digest> = {
  run_date: '2026-06-24',
  summary: 'Dollar softens as cuts get priced.',
  key_themes: ['USD', 'rate cuts'],
  doc_count: 12,
  broker_count: 7,
};

function render(digest: Digest, now?: string): string {
  return renderToStaticMarkup(createElement(DigestBrief, { digest, now }));
}

describe('DigestBrief — digest summary markdown', () => {
  it('renders the empty state when there is no digest', () => {
    const html = render(null);
    expect(html).toContain('No digest for today yet.');
    expect(html).toContain('data-slot="card"');
    expect(html).toContain('data-reveal');
    expect(html).not.toContain('glass-card');
  });

  it('renders the summary through the markdown renderer inside the .chat-md scope', () => {
    const html = render({ ...baseDigest, summary: '**Hot** dollar into the print.' });
    expect(html).toContain('chat-md');
    expect(html).toContain('<strong>Hot</strong>');
    expect(html).not.toContain('**Hot**');
  });

  it('keeps plain-text line layout: soft breaks survive as newlines under whitespace-pre-line', () => {
    const html = render({ ...baseDigest, summary: 'Line one\nLine two' });
    // react-markdown emits the soft break as a literal "\n" text node …
    expect(html).toContain('Line one\nLine two');
    // … and the scope carries whitespace-pre-line so it renders as a break.
    expect(html).toContain('whitespace-pre-line');
  });

  it('renders the meta counts and key-theme chips', () => {
    const html = render(baseDigest);
    expect(html).toContain('12 docs');
    expect(html).toContain('7 brokers');
    expect(html).toContain('USD');
    expect(html).toContain('rate cuts');
  });
});

/**
 * The digest is whatever the freshest covered session is (getLatestDigest has
 * no today gate), so the card must name the run date and age it in weekday
 * trading sessions — never calendar days, or every weekend reads as stale.
 */
describe('DigestBrief — run date and trading-session age', () => {
  it('always shows the run date, and the date alone at 0-1 sessions', () => {
    // Same session: no session has come between the run and the read.
    const sameDay = render({ ...baseDigest, run_date: '2026-10-19' }, '2026-10-19');
    expect(sameDay).toContain('as of 2026-10-19');
    expect(sameDay).not.toContain('data-digest-age');
    // Friday's digest read on Monday: one session (Monday) has come.
    const html = render({ ...baseDigest, run_date: '2026-10-16' }, '2026-10-19');
    expect(html).toContain('as of 2026-10-16');
    expect(html).not.toContain('data-digest-age');
  });

  it('never bakes the build date into the age on the server snapshot', () => {
    // Without an injected `now`, static SSR renders the date only. A digest old
    // enough to be stale against any plausible build date still gets no badge,
    // so the static export cannot serve its own build day as the reader's.
    const html = render({ ...baseDigest, run_date: '2020-01-02' });
    expect(html).toContain('as of 2020-01-02');
    expect(html).not.toContain('data-digest-age');
  });

  it('does not age a Friday digest over the weekend', () => {
    const html = render({ ...baseDigest, run_date: '2026-10-16' }, '2026-10-18');
    expect(html).toContain('as of 2026-10-16');
    expect(html).not.toContain('data-digest-age');
    expect(html).not.toContain('warn');
    expect(html).not.toContain('stale');
  });

  it('warns at 2 trading sessions', () => {
    // Thursday's digest read on Monday: Friday and Monday are two sessions.
    const html = render({ ...baseDigest, run_date: '2026-10-15' }, '2026-10-19');
    expect(html).toContain('as of 2026-10-15');
    expect(html).toContain('data-digest-age="warn"');
    expect(html).toContain('warn');
    expect(html).not.toContain('stale');
  });

  it('marks the digest stale at 3+ trading sessions', () => {
    // The measured defect: Wednesday 14 Oct read on Monday 19 Oct.
    const html = render({ ...baseDigest, run_date: '2026-10-14' }, '2026-10-19');
    expect(html).toContain('as of 2026-10-14');
    expect(html).toContain('data-digest-age="stale"');
    expect(html).toContain('stale');
  });
});
