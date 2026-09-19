'use client';

import { useEffect, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
  isFxHubOnlyAllowedPath,
  useFxHubOnlyInvitee,
} from '@/lib/fx-hub-only';

/**
 * Route guard for the 12x single-view contract: an fx_hub-only invitee who
 * lands on any non-FX-Hub route (bookmark, deep link, stale history) is
 * redirected to the FX Hub instead of seeing DiGiQuant surfaces they were
 * never given. The sidebar and command palette hide those entries; this
 * closes the direct-URL path.
 */
export default function FxHubOnlyGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { fxHubOnlyInvitee } = useFxHubOnlyInvitee();
  const blocked = fxHubOnlyInvitee && !isFxHubOnlyAllowedPath(pathname ?? '/');

  useEffect(() => {
    if (blocked) router.replace('/twelve-x');
  }, [blocked, router]);

  if (blocked) return null;
  return <>{children}</>;
}
