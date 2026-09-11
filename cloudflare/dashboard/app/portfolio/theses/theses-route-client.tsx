'use client';

import { useSearchParams } from 'next/navigation';
import { ThesesHubToPortfolioRedirectPage } from '@/components/legacy-spa-redirect';
import ThesisDetailPageInner from '@/components/portfolio/theses/ThesisDetailPageInner';

/**
 * One static route, two jobs, selected by `?thesis=` (#1760):
 *   - `/portfolio/theses`                  → legacy hub, redirects to the Theses tab
 *   - `/portfolio/theses?thesis=<id>`      → that thesis' detail view
 *
 * `key` remounts the detail view when the id changes so thesis history state
 * stays in sync (the behaviour the removed `[thesisId]` client provided).
 */
export default function ThesesRouteClient() {
  const searchParams = useSearchParams();
  const thesisId = (searchParams.get('thesis') ?? '').trim();

  if (!thesisId) return <ThesesHubToPortfolioRedirectPage />;
  return <ThesisDetailPageInner key={thesisId} thesisId={thesisId} />;
}
