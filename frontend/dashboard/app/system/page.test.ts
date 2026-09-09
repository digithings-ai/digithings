import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

import Page from './page';

describe('/system route', () => {
  it('is a redirect stub to Pipeline (System nav removed)', () => {
    const html = renderToStaticMarkup(createElement(Page));
    expect(html).toContain('Redirecting to Pipeline');
    expect(html).not.toContain('How dashboard works');
  });
});
