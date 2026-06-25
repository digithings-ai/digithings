'use client';

import { ReactNode, Suspense } from 'react';
import { usePathname } from 'next/navigation';
import Sidebar from '@/components/sidebar';
import MobileAppBar from '@/components/mobile-app-bar';
import CommandPalette from '@/components/command-palette';

/**
 * App frame: the Olympus shell (sidebar + page chrome) for normal routes.
 *
 * The twelve-x FX Research suite is a STANDALONE surface — reachable only by direct
 * URL, with no sidebar, breadcrumbs, or cross-navigation. For any path under
 * `/twelve-x` we render the page bare (just a scroll container) so it reads as its
 * own self-contained app rather than an Olympus tab.
 */
export default function AppFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const standalone = pathname?.startsWith('/twelve-x') ?? false;

  if (standalone) {
    return (
      <main className="flex min-h-screen min-w-0 flex-1 flex-col overflow-y-auto max-h-screen">
        {children}
      </main>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Suspense fallback={<aside className="w-[260px] shrink-0 border-r border-border-subtle bg-bg-glass" />}>
        <Sidebar />
      </Suspense>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto max-h-screen">
        <MobileAppBar />
        <CommandPalette />
        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
      </main>
    </div>
  );
}
