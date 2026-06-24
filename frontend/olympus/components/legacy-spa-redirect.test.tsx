import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Node-environment test (no jsdom): we run effects synchronously by stubbing
 * React's `useEffect` to invoke its callback immediately, and capture the
 * router target by stubbing `next/navigation`. We then invoke each redirect's
 * function component directly and assert it routes to the Pipeline grammar.
 */
const replace = vi.fn();
let search = new URLSearchParams();

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react');
  return {
    ...actual,
    useEffect: (fn: () => void) => fn(),
    // Suspense/children passthrough not needed; we call the *Inner* components.
  };
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => search,
}));

vi.mock('@/components/AtlasLoader', () => ({ default: () => null }));

import {
  LibraryToWhyRedirectPage,
  StrategyToAnalysisRedirectPage,
  ResearchToWhyRedirectPage,
} from './legacy-spa-redirect';

// The exported pages wrap the *Inner* in a Suspense whose fallback is the loader;
// rendering the page calls the wrapped tree's component function via React. We
// instead drive the inner effect by invoking the page component, which under our
// useEffect stub runs the redirect synchronously when the Inner mounts. Because
// Suspense is not a function we can call directly, we render the page to a string
// to force the Inner to execute.
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';

beforeEach(() => {
  replace.mockClear();
  search = new URLSearchParams();
});

describe('legacy redirects → Pipeline grammar (F2)', () => {
  it('Library → /pipeline node, preserving date + inferring stage from docKey', () => {
    search = new URLSearchParams({ date: '2026-06-23', docKey: 'analyst/IJR' });
    renderToStaticMarkup(createElement(LibraryToWhyRedirectPage));
    expect(replace).toHaveBeenCalledWith(
      '/pipeline?date=2026-06-23&stage=selection&node=analyst%2FIJR'
    );
  });

  it('Strategy (no thesis) → /pipeline selection stage', () => {
    renderToStaticMarkup(createElement(StrategyToAnalysisRedirectPage));
    expect(replace).toHaveBeenCalledWith('/pipeline?stage=selection');
  });

  it('Strategy (with thesis) still deep-links the thesis detail', () => {
    search = new URLSearchParams({ thesis: 'MT1' });
    renderToStaticMarkup(createElement(StrategyToAnalysisRedirectPage));
    expect(replace).toHaveBeenCalledWith('/portfolio/theses/MT1');
  });

  it('Research → /pipeline, preserving date', () => {
    search = new URLSearchParams({ date: '2026-06-22' });
    renderToStaticMarkup(createElement(ResearchToWhyRedirectPage));
    expect(replace).toHaveBeenCalledWith('/pipeline?date=2026-06-22');
  });
});
