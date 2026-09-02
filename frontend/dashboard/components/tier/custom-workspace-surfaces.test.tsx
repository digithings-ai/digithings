import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  BrokerStatusSurface,
  OverlayProfileSurface,
  PrivateBookSurface,
} from './custom-workspace-surfaces';

describe('Studio workspace surfaces (tier gates)', () => {
  it.each([
    { name: 'private_book', Comp: PrivateBookSurface },
    { name: 'overlay_profile', Comp: OverlayProfileSurface },
  ] as const)('$name locks for Desk', ({ Comp }) => {
    const html = renderToStaticMarkup(createElement(Comp, { tier: 'desk' }));
    expect(html).toContain('locked-surface');
    expect(html).not.toContain('tier-unlocked-note');
  });

  it('broker_status unlocks on Desk', () => {
    const html = renderToStaticMarkup(
      createElement(
        BrokerStatusSurface,
        { tier: 'desk' },
        createElement('div', { 'data-testid': 'broker_status' }, 'ok'),
      ),
    );
    expect(html).toContain('data-testid="broker_status"');
    expect(html).not.toContain('locked-surface');
  });

  it.each([
    { name: 'private_book', Comp: PrivateBookSurface },
    { name: 'broker_status', Comp: BrokerStatusSurface },
    { name: 'overlay_profile', Comp: OverlayProfileSurface },
  ] as const)('$name passthrough for Studio', ({ Comp, name }) => {
    const html = renderToStaticMarkup(
      createElement(Comp, { tier: 'studio' }, createElement('div', { 'data-testid': name }, 'ok')),
    );
    expect(html).toContain(`data-testid="${name}"`);
    expect(html).not.toContain('locked-surface');
  });

  it('private_book locked-then-empty still renders locked chrome', () => {
    const html = renderToStaticMarkup(
      createElement(PrivateBookSurface, { tier: 'free' }, null),
    );
    expect(html).toContain('locked-surface');
    expect(html).toContain('private_book');
  });
});
