import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import SystemPage from './page';

// Static render: the data fetch runs in an effect (not during SSR), so the
// data-gated sections show the loader — but the page structure (Run health,
// the Diagnostics disclosure, and the always-on "How Olympus works" explainer)
// renders, which is what we assert.
describe('SystemPage', () => {
  it('is the demoted footnote: Run health + How Olympus works, scorecard gone', () => {
    const html = renderToStaticMarkup(createElement(SystemPage));

    expect(html).toContain('Run health');
    expect(html).toContain('How Olympus works');
    // Attribution + position risk live behind a collapsed Diagnostics disclosure.
    expect(html).toContain('<details');
    expect(html).toContain('Diagnostics');
    // The conviction scorecard moved to Portfolio → Performance; not shown here.
    expect(html).not.toContain('Decision Scorecard');
  });
});
