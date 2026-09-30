'use client';

import { useState, useSyncExternalStore, type MouseEvent } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { LogOut, Moon, Search, Settings, Sun } from 'lucide-react';
import { GLOOMBERB_TERMINAL_URL, NavShell, type NavLink } from '@digithings/ui';
import { Dialog, DialogContent, IconButton, Kbd } from '@digithings/ui/ui';
import { DashboardMark } from '@/components/dashboard-mark';
import { useAppShell } from '@/components/app-shell-context';
import { SettingsContent } from '@/components/settings-content';
import { useDashboardTheme } from '@/components/theme-provider';
import { useAuth } from '@/lib/auth-context';
import { useDashboard } from '@/lib/dashboard-context';
import { dataSourceHost } from '@/lib/data-source-host';
import { useFxHubOnlyInvitee } from '@/lib/fx-hub-only';
import { NAV, activeNavHref } from '@/lib/nav';
import { dashboardBasePath } from '@/lib/supabase';

/** Spine href → the static-export URL NavShell renders (basePath + trailing slash). */
const withBase = (base: string, href: string) => (href === '/' ? `${base}/` : `${base}${href}/`);

/**
 * The dashboard's one top bar: the kit NavShell composed with the app's spine,
 * search, settings, theme and session. NavShell renders plain anchors (marketing
 * sites hard-navigate); the dashboard is a client-routed SPA whose data provider
 * must survive navigation, so a capture handler on the wrapper turns in-app link
 * clicks — bar and portal sheet alike, React events bubble through portals —
 * into router pushes. Modified/middle clicks and external links pass untouched.
 */
export default function ShellBar() {
  const pathname = usePathname();
  const router = useRouter();
  const base = dashboardBasePath();
  const { openCommandPalette } = useAppShell();
  const { authEnabled, user, signOut } = useAuth();
  const { effectiveTheme, setTheme } = useDashboardTheme();
  const { data } = useDashboard();
  const { canFxHub, fxHubOnlyInvitee } = useFxHubOnlyInvitee();
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  // An fx_hub-only invitee sees FX Hub and nothing else (12x single-view contract).
  const spine: NavLink[] = NAV.filter((n) => {
    if (n.demoted) return false;
    if (n.href === '/twelve-x') return canFxHub;
    return !fxHubOnlyInvitee;
  }).map((n) => ({ label: n.label, href: withBase(base, n.href) }));
  // The external terminal (#4204) is a flat anchor, never a route.
  const links: NavLink[] = fxHubOnlyInvitee
    ? spine
    : [...spine, { label: 'Gloomberb', href: GLOOMBERB_TERMINAL_URL, external: true }];

  const active = activeNavHref(pathname, base);
  const currentPath = active ? withBase(base, active) : undefined;
  const meta = data?.portfolio?.meta ?? null;

  const identityLabel =
    user?.email?.trim() ||
    (typeof user?.user_metadata?.full_name === 'string' ? user.user_metadata.full_name : null) ||
    (typeof user?.user_metadata?.name === 'string' ? user.user_metadata.name : null) ||
    'Signed in';

  function routeInApp(e: MouseEvent<HTMLElement>) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const anchor = (e.target as HTMLElement).closest('a[href]');
    if (!anchor || anchor.getAttribute('target') === '_blank') return;
    const href = anchor.getAttribute('href') ?? '';
    if (href !== `${base}/` && !href.startsWith(`${base}/`)) return;
    e.preventDefault();
    router.push(href.slice(base.length) || '/');
  }

  async function handleSignOut() {
    setSignOutError(null);
    try {
      await signOut();
    } catch (err) {
      setSignOutError(err instanceof Error ? err.message : 'Sign-out failed');
    }
  }

  return (
    <div data-print-hide onClickCapture={routeInApp}>
      <NavShell
        brand={
          <span className="inline-flex items-center gap-2">
            <DashboardMark />
            <span className="font-mono text-[0.8rem] tracking-tight text-ink">
              digi<span className="text-accent">quant</span>
            </span>
          </span>
        }
        homeHref={withBase(base, '/')}
        homeLabel="digiquant dashboard home"
        links={links}
        currentPath={currentPath}
        skipTo="#main"
        showThemeToggle={false}
        actions={
          <>
            <IconButton
              type="button"
              onClick={openCommandPalette}
              aria-label="Search"
              className="gap-1.5 px-2 max-[880px]:hidden"
            >
              <Search size={15} aria-hidden />
              <Kbd>⌘K</Kbd>
            </IconButton>
            <IconButton
              type="button"
              onClick={() => setTheme(effectiveTheme === 'dark' ? 'light' : 'dark')}
              aria-label="Toggle colour theme"
              title="Toggle theme"
            >
              {/* The stored preference is unknown on the server; icon appears post-mount. */}
              {!mounted ? null : effectiveTheme === 'dark' ? (
                <Sun size={15} aria-hidden />
              ) : (
                <Moon size={15} aria-hidden />
              )}
            </IconButton>
            <IconButton
              type="button"
              onClick={() => setSettingsOpen((v) => !v)}
              aria-label="Settings"
              aria-haspopup="dialog"
              aria-expanded={settingsOpen}
            >
              <Settings size={15} aria-hidden />
            </IconButton>
            {authEnabled && user ? (
              <span data-testid="shell-auth-identity" className="inline-flex items-center">
                <IconButton
                  type="button"
                  onClick={() => void handleSignOut()}
                  aria-label="Sign out"
                  title={`Sign out ${identityLabel}`}
                >
                  <LogOut size={15} aria-hidden />
                </IconButton>
                {signOutError ? (
                  <span role="alert" className="ms-2 font-mono text-[0.68rem] text-danger">
                    {signOutError}
                  </span>
                ) : null}
              </span>
            ) : null}
          </>
        }
        cta={
          <button
            type="button"
            onClick={openCommandPalette}
            className="w-full border border-hair px-3 py-2 text-start font-mono text-[0.8rem] text-ink-soft"
          >
            Search…
          </button>
        }
      />
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent
          aria-label="Settings"
          className="max-h-[min(70vh,520px)] w-[min(280px,calc(100vw-2rem))] max-w-[280px] gap-0 overflow-y-auto sm:max-w-[280px]"
        >
          <SettingsContent
            variant="popover"
            lastRunDate={meta?.last_updated ?? null}
            lastRunAt={meta?.last_run_at ?? null}
            runType={meta?.latest_snapshot_run_type ?? null}
            version={process.env.NEXT_PUBLIC_DASHBOARD_VERSION ?? 'v0.1 · dev'}
            dataSourceHost={dataSourceHost()}
            onOpenPalette={() => {
              setSettingsOpen(false);
              openCommandPalette();
            }}
            onNavigate={() => setSettingsOpen(false)}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
