'use client';

import { useState } from 'react';
import Link from 'next/link';
import { LogOut, SlidersHorizontal } from 'lucide-react';
import {
  Alert,
  AlertDescription,
  Avatar,
  AvatarFallback,
  Badge,
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@digithings/ui/ui';
import { useAppShell, type Density } from '@/components/app-shell-context';
import { useDashboardTheme, type DashboardTheme } from '@/components/theme-provider';
import { useAuth } from '@/lib/auth-context';
import { usePlanTier } from '@/lib/use-entitlement';

const TRIGGER =
  'flex w-full items-center gap-2 border-none bg-transparent p-2 text-start font-mono text-[0.78rem] text-ink-soft outline-none hover:bg-accent-weak hover:text-ink focus-visible:ring-1 focus-visible:ring-ring/50';

/**
 * Account footer. With auth: identity + tier badge. Without: a plain "Preferences"
 * trigger. Either way the menu is the device-local quick-settings surface
 * (theme, density, sidebar default) — full settings live at /settings.
 */
export default function SidebarAccount({ collapsed }: { collapsed: boolean }) {
  const { authEnabled, user, signOut } = useAuth();
  const { theme, setTheme } = useDashboardTheme();
  const { density, setDensity, sidebarDefault, setSidebarDefault, openCommandPalette } = useAppShell();
  const tier = usePlanTier();
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const signedIn = authEnabled && !!user;

  const identity =
    user?.email?.trim() ||
    (typeof user?.user_metadata?.full_name === 'string' ? user.user_metadata.full_name : null) ||
    (typeof user?.user_metadata?.name === 'string' ? user.user_metadata.name : null) ||
    'Signed in';

  async function handleSignOut() {
    setSignOutError(null);
    try {
      await signOut();
    } catch (err) {
      setSignOutError(err instanceof Error ? err.message : 'Sign-out failed');
    }
  }

  return (
    <div className="shrink-0 border-t border-hair">
      {signOutError ? (
        <Alert variant="destructive" className="rounded-none border-x-0 border-t-0">
          <AlertDescription>{signOutError}</AlertDescription>
        </Alert>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger
          className={`${TRIGGER} ${collapsed ? 'justify-center' : ''}`}
          aria-label={signedIn ? `Account menu, ${identity}` : 'Preferences'}
        >
          {signedIn ? (
            <Avatar size="sm">
              <AvatarFallback>{identity.charAt(0).toUpperCase()}</AvatarFallback>
            </Avatar>
          ) : (
            <SlidersHorizontal className="size-4 shrink-0" aria-hidden />
          )}
          {collapsed ? null : signedIn ? (
            <>
              <span className="min-w-0 flex-1 truncate" title={identity} data-testid="sidebar-auth-identity">
                {identity}
              </span>
              <Badge variant="neutral">{tier}</Badge>
            </>
          ) : (
            <span className="flex-1">Preferences</span>
          )}
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" align="start" className="w-56">
          <DropdownMenuGroup>
            <DropdownMenuLabel>Theme</DropdownMenuLabel>
            <DropdownMenuRadioGroup value={theme} onValueChange={(v) => setTheme(v as DashboardTheme)}>
              <DropdownMenuRadioItem value="auto">Auto</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="dark">Dark</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="light">Light</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuLabel>Density</DropdownMenuLabel>
            <DropdownMenuRadioGroup value={density} onValueChange={(v) => setDensity(v as Density)}>
              <DropdownMenuRadioItem value="compact">Compact</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="comfortable">Comfortable</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuCheckboxItem
            checked={sidebarDefault === 'collapsed'}
            onCheckedChange={(c) => setSidebarDefault(c ? 'collapsed' : 'expanded')}
          >
            Collapse sidebar by default
          </DropdownMenuCheckboxItem>
          <DropdownMenuItem onClick={openCommandPalette}>
            Command palette
            <DropdownMenuShortcut>⌘K</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem render={<Link href="/settings" />}>All settings</DropdownMenuItem>
          {signedIn ? (
            <DropdownMenuItem variant="destructive" onClick={() => void handleSignOut()}>
              <LogOut />
              Sign out
            </DropdownMenuItem>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
