import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SystemStatus } from './system-page';
import type { AtlasRunDiagnostics } from '@/lib/types';

function render(diagnostics: AtlasRunDiagnostics[]): string {
  return renderToStaticMarkup(createElement(SystemStatus, { diagnostics }));
}

describe('SystemStatus — empty', () => {
  it('shows "No runs recorded yet" when there are no diagnostics', () => {
    const html = render([]);
    expect(html).toContain('No runs recorded yet');
  });
});
