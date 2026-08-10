import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import Page from './page';

// The /system route is the System surface entry point: a live-status hero over a
// demoted "how it works" reference. The data fetch runs in an effect (not during
// SSR), so we assert the always-rendered page chrome here. The scorecard moved to
// Portfolio → Performance and is not shown on System.
describe('/system route', () => {
  it('renders the System header asking the four questions', () => {
    const html = renderToStaticMarkup(createElement(Page));

    expect(html).toContain('How Olympus works');
    expect(html).toContain('Is it running, is it healthy, what does it cost, and how does it work?');
    expect(html).not.toContain('Decision Scorecard');
  });
});
