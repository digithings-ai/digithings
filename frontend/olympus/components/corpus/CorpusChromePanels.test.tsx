import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: (p: { children?: unknown; href?: string }) =>
    createElement('a', { href: p.href }, p.children as never),
}));

import {
  BookChromePanel,
  CorpusIdentityPanel,
  ProfilePinsPanel,
} from './CorpusChromePanels';
import { HOUSE_PROFILE_PIN, TYPED_CHROME_GAP_COPY } from '@/lib/house-chrome';

describe('CorpusChromePanels', () => {
  it('shows corpus key kinds and typed gap — no invented pins', () => {
    const html = renderToStaticMarkup(createElement(CorpusIdentityPanel));
    expect(html).toContain('theme:');
    expect(html).toContain('asset:');
    expect(html).toContain('segment:');
    expect(html).toContain(TYPED_CHROME_GAP_COPY.corpus_service_role_only.slice(0, 40));
  });

  it('labels digithings house book and deep-links Portfolio inspect surfaces', () => {
    const html = renderToStaticMarkup(createElement(BookChromePanel));
    expect(html).toContain('digithings house book');
    expect(html).toContain('href="/portfolio"');
    expect(html).toContain('href="/portfolio/ledger"');
    expect(html).toContain('href="/portfolio/period"');
  });

  it('renders read-only house profile pin chrome', () => {
    const html = renderToStaticMarkup(createElement(ProfilePinsPanel));
    expect(html).toContain(HOUSE_PROFILE_PIN.label);
    expect(html).toContain(HOUSE_PROFILE_PIN.profileKey);
    expect(html).toContain(HOUSE_PROFILE_PIN.versionId);
    expect(html).toContain(TYPED_CHROME_GAP_COPY.profile_live_read_blocked.slice(0, 40));
  });
});
