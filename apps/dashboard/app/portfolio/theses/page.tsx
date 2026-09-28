import { Suspense } from 'react';
import ThesesRouteClient from './theses-route-client';
import PageSkeleton from '@/components/page-skeleton';

/**
 * Theses route (#1760) — a single STATIC page that reads `?thesis=` (client
 * `useSearchParams`), replacing the `[thesisId]` dynamic segment: under
 * `output: 'export'` a dynamic segment only pre-builds the ids enumerated by
 * `generateStaticParams` at build time and hard-404s every thesis created since
 * the last deploy, which is exactly what #1760 reported (5 of 32 live thesis
 * links dead, systematically the newest research). Mirrors the ticker dossier
 * route, which documents the same reasoning (`app/portfolio/tickers/page.tsx`).
 *
 * With no `?thesis=` this is still the legacy hub redirect → `/portfolio?tab=theses`.
 */
export default function PortfolioThesesPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <ThesesRouteClient />
    </Suspense>
  );
}
