'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import CommandPalette from '@/components/command-palette';
import DigichatPopup from '@/components/digichat-popup';
import FxHubOnlyGuard from '@/components/fx-hub-only-guard';
import DbUnavailable from '@/components/db-unavailable';
import ShellBar from '@/components/shell/shell-bar';
import { useDashboard } from '@/lib/dashboard-context';
import { isDbExempt } from '@/lib/nav';

/**
 * The dashboard shell: kit NavShell bar + one `<main>`. Contract, carried over
 * from the retired sidebar frame:
 *   - exactly one `main` landmark (pages render into it, never their own);
 *   - the bar never covers content — main reserves `--nav-shell-h` above it;
 *   - the DB-down gate swaps only the page for the standard card; the bar and
 *     palette stay mounted, and DB-exempt routes (/pipeline, /settings, …,
 *     lib/nav.ts) stay live so the owner can diagnose and reconfigure;
 *   - twelve-x renders in here like every other destination (DB-exempt: it
 *     reads its own research feed).
 */
export default function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { dbStatus } = useDashboard();
  const gated = dbStatus !== 'ok' && !isDbExempt(pathname);

  return (
    <>
      <ShellBar />
      <CommandPalette />
      <main id="main" className="flex min-h-screen min-w-0 flex-col pt-(--nav-shell-h)">
        <div className="flex min-h-0 flex-1 flex-col">
          {gated ? <DbUnavailable /> : <FxHubOnlyGuard>{children}</FxHubOnlyGuard>}
        </div>
      </main>
      {/* Desk+ research/portfolio digichat popup (#3422); no-ops when env off. */}
      <DigichatPopup />
    </>
  );
}
