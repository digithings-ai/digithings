'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, LogOut, Search } from 'lucide-react';
import { GLOOMBERB_TERMINAL_URL } from '@digithings/ui';
import {
  Alert,
  AlertDescription,
  Button,
  Separator,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@digithings/ui/ui';
import { DashboardMark } from '@/components/dashboard-mark';
import { GloomberbMark } from '@/components/gloomberb-mark';
import { useAppShell } from '@/components/app-shell-context';
import SidebarSettings from '@/components/sidebar-settings';
import { useAuth } from '@/lib/auth-context';
import { NAV, navItemForPath, type NavItem } from '@/lib/nav';
import { dashboardBasePath } from '@/lib/supabase';
import { useFxHubOnlyInvitee } from '@/lib/fx-hub-only';

/**
 * The dashboard's primary chrome: a fixed, out-of-flow rail on desktop and a
 * drawer under `md`. The owner spine is `NAV` (lib/nav.ts) — single-sourced with
 * the mobile app bar so the two can never drift.
 *
 * Layout contract: the rail is `fixed`, so `main` owns the explicit desktop
 * offset (`mainOffsetClass`); it must never `md:relative` into flow. That is
 * asserted in `components/app-frame.test.tsx` and is the critical #4426
 * regression guard.
 *
 * Rebuilt from zero on the shared grammar: flat surface, small mono type, kit
 * primitives at default dress. No atmosphere, no glow, no bespoke mark motion.
 */
export default function Sidebar() {
  const pathname = usePathname();
  const base = dashboardBasePath();
  // The nav→route map is the canonical `navItemForPath` (lib/nav.ts): a live
  // route that is not a NAV destination (e.g. /why) resolves to null instead of
  // being silently collapsed onto Pipeline.
  const activeHref = navItemForPath(pathname, base);
  const { sidebarCollapsed, toggleSidebar, mobileNavOpen, setMobileNavOpen, openCommandPalette } =
    useAppShell();
  const { authEnabled, user, signOut } = useAuth();
  const [signOutError, setSignOutError] = useState<string | null>(null);
  // An FX-Hub-invited account with no paid plan (the 12x trader invite path)
  // sees ONLY FX Hub — no Brief/Portfolio/Pipeline nav, not even teaser content.
  const { canFxHub, fxHubOnlyInvitee } = useFxHubOnlyInvitee();

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname, setMobileNavOpen]);

  async function handleSignOut() {
    setSignOutError(null);
    try {
      await signOut();
    } catch (err) {
      setSignOutError(err instanceof Error ? err.message : 'Sign-out failed');
    }
  }

  const identityLabel =
    user?.email?.trim() ||
    (typeof user?.user_metadata?.full_name === 'string' ? user.user_metadata.full_name : null) ||
    (typeof user?.user_metadata?.name === 'string' ? user.user_metadata.name : null) ||
    'Signed in';

  const linkClass = (isActive: boolean, muted: boolean) =>
    [
      'flex items-center gap-3 py-2.5 text-[13px] transition-colors',
      sidebarCollapsed ? 'md:justify-center md:px-3' : 'px-5',
      isActive
        ? 'bg-ink/[0.05] font-medium text-ink'
        : muted
          ? 'text-ink-mute hover:bg-ink/[0.03] hover:text-ink-soft'
          : 'text-ink-soft hover:bg-ink/[0.03] hover:text-ink',
    ].join(' ');

  const renderLink = (item: NavItem) => {
    const { href, label, icon: Icon, demoted } = item;
    const isActive = activeHref === href;
    const link = (
      <Link
        key={href}
        href={href}
        onClick={() => setMobileNavOpen(false)}
        aria-current={isActive ? 'page' : undefined}
        data-demoted={demoted ? 'true' : undefined}
        className={linkClass(isActive, Boolean(demoted))}
      >
        <Icon size={16} className="shrink-0" />
        <span className={sidebarCollapsed ? 'md:sr-only' : ''}>{label}</span>
      </Link>
    );
    if (!sidebarCollapsed) return link;
    // Collapsed rail: the label is sr-only, so surface it as the shared
    // @digithings/ui Tooltip (hover + focus, announced) instead of title=.
    return (
      <Tooltip key={href}>
        <TooltipTrigger render={link} />
        <TooltipContent side="right">{label}</TooltipContent>
      </Tooltip>
    );
  };

  // Dedicated terminal entry (#4204) — the external terminal research tool,
  // deliberately a flat external anchor rather than a nav route.
  const showGloomberb = !fxHubOnlyInvitee;
  const gloomberbLink = (
    <a
      href={GLOOMBERB_TERMINAL_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Gloomberb Terminal (opens in a new tab)"
      data-testid="sidebar-gloomberb-link"
      className={linkClass(false, true)}
    >
      <GloomberbMark size={16} className="shrink-0" />
      <span className={sidebarCollapsed ? 'md:sr-only' : ''}>Gloomberb Terminal</span>
    </a>
  );

  const renderGloomberbLink = () => {
    if (!showGloomberb) return null;
    if (!sidebarCollapsed) return gloomberbLink;
    return (
      <Tooltip>
        <TooltipTrigger render={gloomberbLink} />
        <TooltipContent side="right">Gloomberb Terminal</TooltipContent>
      </Tooltip>
    );
  };

  const primary = NAV.filter((n) => {
    if (n.demoted) return false;
    if (n.href === '/twelve-x') return canFxHub;
    if (fxHubOnlyInvitee) return false;
    return true;
  });
  const demoted = NAV.filter((n) => n.demoted);

  return (
    <>
      {mobileNavOpen ? (
        <div
          className="fixed inset-0 z-[999] bg-ink/40 md:hidden"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden
        />
      ) : null}

      <aside
        id="app-sidebar-nav"
        aria-label="Sidebar"
        className={[
          'fixed top-0 left-0 z-[1000] flex h-screen shrink-0 flex-col border-r border-hair bg-surface transition-[width] duration-300 ease-out',
          'w-[260px]',
          mobileNavOpen ? 'translate-x-0' : '-translate-x-full',
          'md:translate-x-0',
          sidebarCollapsed ? 'md:w-[72px]' : 'md:w-[260px]',
        ].join(' ')}
      >
        <div className="flex min-h-[72px] shrink-0 items-center border-b border-hair px-5">
          <div
            className={`flex w-full items-center justify-between gap-2 ${
              sidebarCollapsed ? 'md:hidden' : ''
            }`}
          >
            <div className="flex min-w-0 items-center gap-2.5" aria-label="digiquant">
              <DashboardMark className="shrink-0" />
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={toggleSidebar}
              className="hidden md:inline-flex"
              aria-label="Collapse sidebar"
            >
              <ChevronLeft size={16} />
            </Button>
          </div>
          <div
            className={`${sidebarCollapsed ? 'hidden md:flex' : 'hidden'} w-full flex-col items-center gap-2`}
          >
            <DashboardMark className="shrink-0" />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={toggleSidebar}
              aria-label="Expand sidebar"
            >
              <ChevronRight size={16} />
            </Button>
          </div>
        </div>

        <nav aria-label="Primary" className="flex flex-1 flex-col py-3">
          {sidebarCollapsed ? null : (
            <Button
              type="button"
              variant="ghost"
              onClick={openCommandPalette}
              className="mx-5 mb-2 hidden justify-start gap-2 px-3 text-xs text-ink-mute md:inline-flex"
              aria-label="Search"
            >
              <Search size={14} className="shrink-0" />
              <span className="flex-1 text-left">Search…</span>
              <kbd className="font-mono text-[10px] text-ink-mute">⌘K</kbd>
            </Button>
          )}
          <TooltipProvider delay={200}>
            {primary.map(renderLink)}
            {showGloomberb || demoted.length > 0 ? (
              <div data-testid="sidebar-bottom-tools" className="mt-auto pt-3">
                <Separator className="mb-3" />
                {demoted.map(renderLink)}
                {renderGloomberbLink()}
              </div>
            ) : null}
          </TooltipProvider>
        </nav>

        <div
          className={`relative z-10 mt-auto border-t border-hair ${
            sidebarCollapsed ? 'px-3 py-4 md:px-2' : 'px-5 py-4'
          }`}
        >
          {authEnabled && user ? (
            <div
              className={`flex flex-col gap-2 ${sidebarCollapsed ? 'md:items-center' : ''}`}
              data-testid="sidebar-auth-identity"
            >
              <p
                className={`truncate font-mono text-[11px] text-ink-soft ${
                  sidebarCollapsed ? 'md:sr-only' : ''
                }`}
                title={identityLabel}
              >
                {identityLabel}
              </p>
              <Button
                type="button"
                variant="ghost"
                onClick={() => void handleSignOut()}
                className={`justify-start gap-2 px-2 text-xs text-ink ${
                  sidebarCollapsed ? 'md:justify-center' : ''
                }`}
                aria-label="Sign out"
              >
                <LogOut size={14} className="shrink-0" />
                <span className={sidebarCollapsed ? 'md:sr-only' : ''}>Sign out</span>
              </Button>
              {signOutError ? (
                <Alert variant="destructive" className="px-2 py-1">
                  <AlertDescription className="font-mono text-[0.68rem]">
                    {signOutError}
                  </AlertDescription>
                </Alert>
              ) : null}
            </div>
          ) : null}
          <SidebarSettings sidebarCollapsed={sidebarCollapsed} />
        </div>
      </aside>
    </>
  );
}
