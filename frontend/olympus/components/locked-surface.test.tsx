import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LockedSurface } from './locked-surface';

describe('LockedSurface', () => {
  it('renders calm locked copy with upgrade CTA to Settings→Billing', () => {
    const html = renderToStaticMarkup(
      createElement(LockedSurface, {
        tier: 'free',
        artifactClass: 'house_weights_nav',
      }),
    );
    expect(html).toContain('data-testid="locked-surface"');
    expect(html).toContain('data-artifact-class="house_weights_nav"');
    expect(html).toContain('data-plan-tier="free"');
    expect(html).toContain('Observer');
    expect(html).toContain('Baseline');
    expect(html).toContain('House weights, NAV, tearsheet, ledger, and attribution unlock on Baseline.');
    expect(html).toContain('href="/settings#billing"');
    expect(html).toContain('Upgrade in Settings → Billing');
    // No fin-green / fin-red / exclamation drama
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
    expect(html).not.toContain('!');
  });

  it('uses Custom unlock copy for private workspace classes', () => {
    const html = renderToStaticMarkup(
      createElement(LockedSurface, {
        tier: 'baseline',
        artifactClass: 'broker_status',
      }),
    );
    expect(html).toContain('Baseline');
    expect(html).toContain('Custom');
    expect(html).toContain('Broker connection status unlocks on Custom.');
  });
});
