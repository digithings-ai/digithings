import { Suspense } from 'react';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import PageSkeleton from '@/components/page-skeleton';
import TwelveXClient from '@/components/twelve-x/TwelveXClient';
import TwelveXHeading from '@/components/twelve-x/TwelveXHeading';

/**
 * OLYMPUS FX Research suite (twelve-x). Thin server wrapper → Suspense →
 * client. Renders inside the standard AppFrame shell (#1664 retired the
 * standalone chrome); the client gates itself on its own research feed
 * (see `isTwelveXConfigured`), which is why the route is DB-exempt. The
 * fallback re-renders the hook-free heading so the static export carries
 * the h1 before hydration (same convention as /pipeline).
 */
export default function TwelveXPage() {
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <Suspense
        fallback={
          <>
            <div className={`${SUBPAGE_MAX} pt-4 md:pt-6`}>
              <header className="border border-hair bg-surface px-4 py-4 md:px-6">
                <TwelveXHeading />
              </header>
            </div>
            <div className="px-6 py-5">
              <PageSkeleton bare />
            </div>
          </>
        }
      >
        <TwelveXClient />
      </Suspense>
    </div>
  );
}
