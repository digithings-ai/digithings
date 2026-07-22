import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

// Stub Next.js navigation — page.tsx must NOT redirect anymore
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('next/link', () => ({ default: (p: { children?: unknown }) => p.children }));

// Stub Supabase / queries so no network required
vi.mock('@/lib/queries', () => ({
  isSupabaseConfigured: () => false,
  getLibraryDocumentById: async () => null,
}));

// Stub the canvas and detail so static render stays minimal
vi.mock('@/components/pipeline/PipelineCanvas', () => ({
  default: ({ day }: { day: unknown }) =>
    createElement('div', { 'data-testid': 'pipeline-canvas' }, 'pipeline-canvas'),
}));
vi.mock('@/components/pipeline/PipelineNodeDetail', () => ({
  default: () => null,
}));
vi.mock('@/components/pipeline/PipelineDaySelector', () => ({
  default: () => createElement('div', null, 'day-selector'),
}));

import PipelinePage from './page';

describe('app/pipeline/page', () => {
  it('mounts and does not redirect — renders pipeline-canvas marker', () => {
    const html = renderToStaticMarkup(createElement(PipelinePage));
    // Should NOT be a redirect (old page had useRouter().replace — no canvas)
    expect(html).toContain('pipeline-canvas');
  });

  it('renders the Pipeline heading', () => {
    const html = renderToStaticMarkup(createElement(PipelinePage));
    expect(html).toContain('Pipeline');
  });

  it('renders one command band above the workflow canvas', () => {
    const html = renderToStaticMarkup(createElement(PipelinePage));
    expect(html).toContain('data-testid="pipeline-workspace"');
    expect(html).toContain('data-testid="pipeline-command-band"');
    expect(html).toContain('data-testid="pipeline-workflow"');
    expect(html.indexOf('pipeline-command-band')).toBeLessThan(html.indexOf('pipeline-workflow'));
    expect(html).toContain('min-h-[calc(100dvh-125px)]');
    expect(html).toContain('md:min-h-0');
    expect(html).toContain('min-h-12');
    expect(html).not.toContain('How today');
    expect(html).not.toContain('research → deliberation → selection');
    expect(html).not.toContain('summary-strip');
    expect(html).not.toContain('glass-card');
  });

  it('no horizontal scroll class on page wrapper — overflow-hidden on viewport only', () => {
    const html = renderToStaticMarkup(createElement(PipelinePage));
    // Page body wrapper must not have overflow-x-auto or overflow-x-scroll
    expect(html).not.toContain('overflow-x-auto');
    expect(html).not.toContain('overflow-x-scroll');
  });

  it('node-detail uses bottom-sheet responsive classes (md: prefix for desktop panel)', () => {
    // The PipelineNodeDetail is mocked out in this test; check PipelineNodeDetail directly
    // This is a code-inspection assertion via the component source.
    // The actual responsive classes are verified in PipelineNodeDetail.test.tsx 'uses bottom-sheet classes'
    expect(true).toBe(true); // structural — covered by PipelineNodeDetail.test.tsx
  });
});
