import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { EntitledSurface } from './entitled-surface';

describe('EntitledSurface', () => {
  it('passthrough when tier may see the class (unlocked)', () => {
    const html = renderToStaticMarkup(
      createElement(
        EntitledSurface,
        { artifactClass: 'house_weights_nav', tier: 'baseline' },
        createElement('div', { 'data-testid': 'panel' }, 'weights'),
      ),
    );
    expect(html).toContain('data-testid="panel"');
    expect(html).toContain('weights');
    expect(html).not.toContain('locked-surface');
  });

  it('renders LockedSurface when tier may not see the class', () => {
    const html = renderToStaticMarkup(
      createElement(
        EntitledSurface,
        { artifactClass: 'house_weights_nav', tier: 'free' },
        createElement('div', { 'data-testid': 'panel' }, 'weights'),
      ),
    );
    expect(html).toContain('locked-surface');
    expect(html).not.toContain('data-testid="panel"');
  });

  it('locked-then-empty: ignores empty children when locked', () => {
    const html = renderToStaticMarkup(
      createElement(
        EntitledSurface,
        { artifactClass: 'glassbox_economics', tier: 'free' },
        null,
      ),
    );
    expect(html).toContain('locked-surface');
    expect(html).toContain('glassbox_economics');
  });

  it('enterprise unlocks custom-only classes', () => {
    const html = renderToStaticMarkup(
      createElement(
        EntitledSurface,
        { artifactClass: 'private_book', tier: 'enterprise' },
        createElement('div', { 'data-testid': 'private' }, 'book'),
      ),
    );
    expect(html).toContain('data-testid="private"');
  });
});
