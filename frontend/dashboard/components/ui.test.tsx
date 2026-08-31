import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Badge, formatPct, pnlColor } from './ui';

/**
 * Badge is a thin shim over the shared @digithings/web controls Badge
 * (dress="reference", F4 #1450). These tests pin the olympus tone → shared
 * tone mapping so a call site's color semantics can never silently drift,
 * and the props passthrough the old local Badge did not have.
 */
describe('Badge (re-backed by @digithings/web controls Badge)', () => {
  const TONES: Array<['default' | 'blue' | 'green' | 'red' | 'amber', string]> = [
    ['blue', 'ctl-badge-ref--accent'],
    ['green', 'ctl-badge-ref--up'],
    ['red', 'ctl-badge-ref--down'],
    ['amber', 'ctl-badge-ref--warn'],
  ];

  it.each(TONES)('maps olympus tone "%s" onto the shared "%s" dress', (variant, cls) => {
    const html = renderToStaticMarkup(<Badge variant={variant}>x</Badge>);
    expect(html).toContain('ctl-badge-ref');
    expect(html).toContain(cls);
  });

  it('renders the neutral pill (no tone modifier) for the default variant', () => {
    const html = renderToStaticMarkup(<Badge>x</Badge>);
    expect(html).toContain('ctl-badge-ref');
    expect(html).not.toContain('ctl-badge-ref--');
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
