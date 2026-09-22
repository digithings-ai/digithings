import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import Page from './page';

describe('/system route', () => {
  it('is a redirect stub to Pipeline (System nav removed)', () => {
    const html = renderToStaticMarkup(createElement(Page));
    // Rides the shared legacy-redirect grammar (loader fallback), not the
    // retired System explainer.
    expect(html).toContain('research-loader-inline');
    expect(html).not.toContain('How dashboard works');
  });
});
