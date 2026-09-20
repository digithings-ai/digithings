import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import DetailPanelHeaderActions, {
  detailPanelSheetSizeClass,
} from './DetailPanelHeaderActions';

describe('DetailPanelHeaderActions', () => {
  it('renders widen, full screen, and close affordances at default size', () => {
    const html = renderToStaticMarkup(
      createElement(DetailPanelHeaderActions, {
        size: 'default',
        onSizeChange: vi.fn(),
        onClose: vi.fn(),
      }),
    );
    expect(html).toContain('aria-label="Widen panel"');
    expect(html).toContain('aria-label="Full screen"');
    expect(html).toContain('aria-label="Close"');
  });

  it('swaps widen for narrow when wide, and hides widen in full screen', () => {
    const wide = renderToStaticMarkup(
      createElement(DetailPanelHeaderActions, {
        size: 'wide',
        onSizeChange: vi.fn(),
        onClose: vi.fn(),
      }),
    );
    expect(wide).toContain('aria-label="Narrow panel"');
    expect(wide).not.toContain('aria-label="Widen panel"');

    const full = renderToStaticMarkup(
      createElement(DetailPanelHeaderActions, {
        size: 'full',
        onSizeChange: vi.fn(),
        onClose: vi.fn(),
      }),
    );
    expect(full).toContain('aria-label="Exit full screen"');
    expect(full).not.toContain('Narrow panel');
    expect(full).not.toContain('Widen panel');
  });

  it('maps sheet size classes for digiweb SheetContent overrides', () => {
    expect(detailPanelSheetSizeClass('default')).toContain('max-w-xl!');
    expect(detailPanelSheetSizeClass('wide')).toContain('960px');
    expect(detailPanelSheetSizeClass('full')).toContain('max-w-none!');
  });
});
