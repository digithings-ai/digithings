import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Badge, formatPct, pnlColor } from './ui';

/**
 * Badge is a thin tone mapper over the vendored kit `Badge`
 * (@digithings/web/ui, variant="outline"). These tests pin the dashboard
 * tone → token-utility mapping so a call site's color semantics can never
 * silently drift, and the props passthrough the old local Badge did not have.
 */
describe('Badge (backed by @digithings/web/ui kit Badge)', () => {
  const TONES: Array<['default' | 'blue' | 'green' | 'red' | 'amber', string]> = [
    ['default', 'text-ink-mute'],
    ['blue', 'border-accent-weak text-accent'],
    ['green', 'border-up/40 text-up'],
    ['red', 'border-down/40 text-down'],
    ['amber', 'border-warn/40 text-warn'],
  ];

  it.each(TONES)('maps dashboard tone "%s" onto "%s"', (variant, cls) => {
    const html = renderToStaticMarkup(<Badge variant={variant}>x</Badge>);
    expect(html).toContain('data-slot="badge"');
    for (const piece of cls.split(' ')) {
      expect(html).toContain(piece);
    }
  });

  it('renders the kit outline badge for the default variant', () => {
    const html = renderToStaticMarkup(<Badge>x</Badge>);
    expect(html).toContain('data-slot="badge"');
    expect(html).not.toContain('ctl-badge-ref');
  });

  it('passes className and data-* attributes through to the span', () => {
    const html = renderToStaticMarkup(
      <Badge variant="green" className="extra" data-testid="tone">
        x
      </Badge>
    );
    expect(html).toContain('extra');
    expect(html).toContain('data-testid="tone"');
    expect(html).toContain('>x<');
  });
});

describe('StatCard', () => {
  it('renders on the kit Card with the data-reveal motion hook', async () => {
    const { StatCard } = await import('./ui');
    const html = renderToStaticMarkup(<StatCard label="NAV" value="$1.2M" subtitle="today" />);
    expect(html).toContain('data-slot="card"');
    expect(html).toContain('data-reveal');
    expect(html).not.toContain('dq-slab');
    expect(html).toContain('NAV');
  });
});

describe('formatPct / pnlColor', () => {
  it('formats signed percentages and dashes nulls', () => {
    expect(formatPct(1.234)).toBe('+1.23%');
    expect(formatPct(-0.5)).toBe('-0.50%');
    expect(formatPct(null)).toBe('—');
  });

  it('maps sign onto the canon money tokens', () => {
    expect(pnlColor(2)).toBe('text-up');
    expect(pnlColor(-2)).toBe('text-down');
    expect(pnlColor(null)).toBe('');
  });
});
