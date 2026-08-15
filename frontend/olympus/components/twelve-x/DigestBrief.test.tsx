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

function render(digest: Digest): string {
  return renderToStaticMarkup(createElement(DigestBrief, { digest }));
}

describe('DigestBrief — digest summary markdown', () => {
  it('renders the empty state when there is no digest', () => {
    expect(render(null)).toContain('No digest for today yet.');
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
