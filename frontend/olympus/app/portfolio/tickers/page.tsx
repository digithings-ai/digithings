import { Suspense } from 'react';
import TickerDossierClient from './ticker-dossier-client';
import PageSkeleton from '@/components/page-skeleton';

/**
 * Ticker dossier route (#1562 PR2) — a single STATIC page reading `?ticker=`
 * (client `useSearchParams`), not a `[ticker]` dynamic segment: under
 * `output: 'export'` a dynamic segment only pre-builds the enumerated union and
 * 404s on any ticker outside it, which breaks "search any ticker." Mirrors the
 * existing `?ticker=` query-param precedent (`ThesisHoldingsExpressing` →
 * `/portfolio?ticker=`).
 */
export default function PortfolioTickerDossierPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <TickerDossierClient />
    </Suspense>
  );
}
