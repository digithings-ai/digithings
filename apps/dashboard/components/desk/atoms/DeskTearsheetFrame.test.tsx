import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { TEARSHEET_MIN_OVERLAP_DAYS } from '@/lib/desk/tearsheet-metrics';
import { DeskTearsheetFrame } from './DeskTearsheetFrame';

describe('DeskTearsheetFrame', () => {
  it('gates alpha and IR on overlap and keeps error off the last figures', () => {
    const short = renderToStaticMarkup(
      createElement(DeskTearsheetFrame, {
        state: 'ready',
        overlapDays: TEARSHEET_MIN_OVERLAP_DAYS - 1,
        alphaPct: 1.2,
        informationRatio: 0.4,
      }),
    );
    const long = renderToStaticMarkup(
      createElement(DeskTearsheetFrame, {
        state: 'ready',
        overlapDays: TEARSHEET_MIN_OVERLAP_DAYS,
        alphaPct: 1.2,
        informationRatio: null,
      }),
    );
    const error = renderToStaticMarkup(
      createElement(DeskTearsheetFrame, {
        state: 'error',
        errorMessage: 'performance unavailable',
        overlapDays: TEARSHEET_MIN_OVERLAP_DAYS,
        alphaPct: 1.2,
        informationRatio: 0.4,
      }),
    );

    expect(short).toContain('data-testid="tearsheet-alpha">—');
    expect(short).toContain('data-testid="tearsheet-ir">—');
    expect(long).toContain('data-testid="tearsheet-alpha">+1.2');
    expect(long).toContain('data-testid="tearsheet-ir">—');
    expect(error).toContain('performance unavailable');
    expect(error).not.toContain('tearsheet-alpha');
    expect(error).toContain('data-chrome-path="/house/portfolio/tearsheet"');
  });
});
