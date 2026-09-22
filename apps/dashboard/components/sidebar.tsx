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
  // sees ONLY FX Hub — no Brief/Portfolio/Pipeline nav, not even teaser
  // content, to avoid the confusion of a research dashboard they weren't
  // given access to. A real paying tier (or the studio-floor creator/admin)
  // is unaffected — this only fires for fx_hub-granted + free tier.
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
        className={`
          flex items-center gap-3 py-3 text-sm font-medium transition-all
          ${sidebarCollapsed ? 'md:justify-center md:px-3' : 'px-6'}
          ${
            isActive
              ? 'text-ink bg-ink/[0.04] qn-sidebar-link-active'
              : demoted
                ? 'text-ink-mute hover:text-ink-soft hover:bg-ink/[0.02]'
                : 'text-ink-soft hover:text-ink hover:bg-ink/[0.03]'
          }
        `}
      >
        <Icon size={demoted ? 18 : 20} className="shrink-0" />
        <span className={`qn-sidebar-label ${sidebarCollapsed ? 'md:sr-only' : ''}`}>{label}</span>
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
  // deliberately a flat external anchor rather than a nav route, pinned to
  // the bottom tools area; per-ticker deep links stay on the surfaces that
  // carry a symbol. Hidden for an fx_hub-only invitee, like every other
  // destination the single-view contract omits.
  const showGloomberb = !fxHubOnlyInvitee;
  const gloomberbLink = (
    <a
      href={GLOOMBERB_TERMINAL_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Gloomberb Terminal (opens in a new tab)"
      data-testid="sidebar-gloomberb-link"
      className={`
        flex items-center gap-3 py-3 text-sm font-medium transition-all
        ${sidebarCollapsed ? 'md:justify-center md:px-3' : 'px-6'}
        text-ink-mute hover:text-ink-soft hover:bg-ink/[0.02]
      `}
    >
      <GloomberbMark size={18} className="shrink-0" />
      <span className={`qn-sidebar-label ${sidebarCollapsed ? 'md:sr-only' : ''}`}>
        Gloomberb Terminal
      </span>
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
          className="fixed inset-0 z-[999] bg-black/60 md:hidden"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden
        />
      ) : null}

      <aside
        id="app-sidebar-nav"
        aria-label="Sidebar"
        className={`
          bg-surface/95 backdrop-blur-md border-r border-hair
          flex flex-col shrink-0
          fixed top-0 left-0 h-screen z-[1000] transition-all duration-300 ease-out
          w-[260px]
          ${mobileNavOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0
          ${sidebarCollapsed ? 'md:w-[72px]' : 'md:w-[260px]'}
        `}
      >
        <div className="border-b border-hair shrink-0 px-6 py-5 min-h-[72px] flex flex-col justify-center">
          <div
            className={`flex items-center justify-between gap-2 w-full ${sidebarCollapsed ? 'md:hidden' : ''}`}
          >
            <div className="flex items-center gap-2.5 min-w-0" aria-label="digiquant">
              <DashboardMark className="shrink-0" />
            </div>
            <Button
              type="button"
              variant="ghost"
              onClick={toggleSidebar}
              className="hidden h-auto shrink-0 rounded-none border border-hair p-2 text-ink-mute hover:bg-ink/[0.06] hover:text-ink md:inline-flex"
              aria-label="Collapse sidebar"
            >
              <ChevronLeft size={18} />
            </Button>
          </div>
          <div
            className={`${sidebarCollapsed ? 'hidden md:flex' : 'hidden'} flex-col items-center gap-3 w-full py-1`}
          >
            <DashboardMark className="shrink-0" />
            <Button
              type="button"
              variant="ghost"
              onClick={toggleSidebar}
              className="h-auto rounded-none border border-hair p-2 text-ink-mute hover:bg-ink/[0.06] hover:text-ink"
              aria-label="Expand sidebar"
            >
              <ChevronRight size={18} />
            </Button>
          </div>
        </div>

        <nav aria-label="Primary" className="flex-1 py-4 flex flex-col">
          {sidebarCollapsed ? null : (
            <Button
              type="button"
              variant="ghost"
              onClick={openCommandPalette}
              className="mx-6 mb-1 hidden h-auto items-center justify-start gap-2 rounded-none border border-hair px-3 py-1.5 text-xs text-ink-mute hover:bg-ink/[0.03] hover:text-ink-soft md:inline-flex"
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
              <div
                data-testid="sidebar-bottom-tools"
                className="mt-auto pt-4 border-t border-hair/60"
              >
                {demoted.map(renderLink)}
                {renderGloomberbLink()}
              </div>
            ) : null}
          </TooltipProvider>
        </nav>

        <div
          className={`border-t border-hair mt-auto overflow-visible relative z-10 ${
            sidebarCollapsed ? 'md:px-2 px-6 py-4' : 'px-6 py-4'
          }`}
        >
          {authEnabled && user ? (
            <div
              className={`acct-session-rail ${sidebarCollapsed ? 'md:items-center' : ''}`}
              data-testid="sidebar-auth-identity"
            >
              <p
                className={`acct-session-email ${sidebarCollapsed ? 'md:sr-only' : ''}`}
                title={identityLabel}
              >
                {identityLabel}
              </p>
              <p className={`acct-session-meta ${sidebarCollapsed ? 'md:sr-only' : ''}`}>signed in</p>
              <Button
                type="button"
                variant="ghost"
                onClick={() => void handleSignOut()}
                className={`h-auto gap-2 rounded-none border border-hair px-3 py-1.5 text-xs text-ink hover:border-accent/50 ${
                  sidebarCollapsed ? 'md:justify-center md:px-2' : ''
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
