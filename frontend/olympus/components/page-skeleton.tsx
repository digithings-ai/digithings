import { Skeleton, SkeletonGroup } from '@digithings/web';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';

/**
 * PageSkeleton — the shared content-shaped fallback for page-level loads
 * (Suspense fallbacks and client data-fetch loading states). Composes the
 * promoted @digithings/web Skeleton primitives: a kicker + title bar, a pair
 * of card blocks, and a body block.
 *
 * Ruling (#1548 LOADING adoption): the AtlasLoader brand moment appears ONLY
 * at the app-boot/root level — app/loading.tsx, the root route's first data
 * paint (app/page.tsx), and the legacy-SPA redirect shim. Every per-page
 * fallback renders this skeleton instead, so in-app navigation reads as
 * "content arriving", not the app rebooting. One loading grammar app-wide:
 * the sk-* shimmer sweep (no animate-pulse).
 */
export default function PageSkeleton({ bare = false }: { bare?: boolean }) {
  const stack = (
    <SkeletonGroup aria-label="Loading page" className="flex flex-col gap-6">
      <div className="flex flex-col gap-2.5">
        <Skeleton size="sm" className="w-24" />
        <Skeleton className="h-7 w-72 max-w-full" />
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Skeleton variant="block" className="h-36 w-full" />
        <Skeleton variant="block" className="h-36 w-full" />
      </div>
      <Skeleton variant="block" className="h-72 w-full" />
    </SkeletonGroup>
  );
  // `bare` drops the page container for callers already inside one
  // (e.g. the performance tear-sheet's ts-page wrapper).
  if (bare) return stack;
  return <div className={`${SUBPAGE_MAX} py-6`}>{stack}</div>;
}
