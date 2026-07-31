import { Suspense } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import TwelveXClient from '@/components/twelve-x/TwelveXClient';
import TwelveXHeading from '@/components/twelve-x/TwelveXHeading';

/**
 * OLYMPUS FX Hub suite (twelve-x). Thin server wrapper → Suspense →
 * client. Renders inside the standard AppFrame shell (#1664 retired the
 * standalone chrome); the client gates itself on its own research feed
 * (see `isTwelveXConfigured`), which is why the route is DB-exempt. The page
 * shows only the tab bar at the top (no title/date banner) — the fallback
 * re-renders the hook-free, off-screen heading so the static export still
 * carries a real h1 before hydration (same convention as /pipeline).
 */
export default function TwelveXPage() {
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <Suspense
        fallback={
          <>
            <TwelveXHeading />
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
