'use client';

import type { MouseEvent } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronRight, ExternalLink, Search } from 'lucide-react';
import { GLOOMBERB_TERMINAL_URL } from '@digithings/ui';
import {
  Kbd,
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from '@digithings/ui/ui';
import { useAppShell } from '@/components/app-shell-context';
import { DashboardMark } from '@/components/dashboard-mark';
import { GloomberbMark } from '@/components/gloomberb-mark';
import { useFxHubOnlyInvitee } from '@/lib/fx-hub-only';
import { usePlanTier } from '@/lib/use-entitlement';
import SidebarAccount from './sidebar-account';
import SidebarStatus from './sidebar-status';
import {
  REFERENCE,
  WORKSPACE,
  activeChildId,
  childHref,
  ownsPath,
  settingsGroup,
  type NavChild,
  type NavGroupItem,
} from './nav-model';
import { notifyUrlState, useNavActive } from './use-nav-active';

/** Same-pathname child links flip URL state in place (no fetch, no scroll) and tell pages. */
function childClickHandler(path: string, close: () => void) {
  return (child: NavChild) => (e: MouseEvent<HTMLElement>) => {
    close();
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (child.path !== path || (!child.param && !child.hash)) return;
    e.preventDefault();
    const url = `${window.location.pathname}${child.param ? `?${child.param.key}=${child.param.value}` : ''}${
      child.hash ? `#${child.hash}` : ''
    }`;
    window.history.pushState(null, '', url);
    if (child.hash) window.dispatchEvent(new HashChangeEvent('hashchange'));
    notifyUrlState();
  };
}

function NavGroup({ item }: { item: NavGroupItem }) {
  const { path, search, hash } = useNavActive();
  const { openGroups, toggleGroup } = useAppShell();
  const { setOpenMobile } = useSidebar();
  const close = () => setOpenMobile(false);
  const active = ownsPath(item, path);
  const childId = activeChildId(item, path, search, hash);
  const hasChildren = item.children.length > 0;
  const open = hasChildren && (active || openGroups.includes(item.id));
  const onChild = childClickHandler(path, close);
  const Icon = item.icon;

  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        tooltip={item.label}
        isActive={active && !childId}
        aria-current={active ? (childId ? 'true' : 'page') : undefined}
        render={<Link href={item.href} onClick={close} />}
      >
        <Icon />
        <span>{item.label}</span>
      </SidebarMenuButton>
      {hasChildren ? (
        <SidebarMenuAction
          aria-expanded={open}
          aria-label={`${open ? 'Collapse' : 'Expand'} ${item.label}`}
          disabled={active}
          onClick={() => toggleGroup(item.id)}
        >
          {open ? <ChevronDown /> : <ChevronRight />}
        </SidebarMenuAction>
      ) : null}
      {open ? (
        <SidebarMenuSub>
          {item.children.map((child) => (
            <SidebarMenuSubItem key={child.id}>
              <SidebarMenuSubButton
                isActive={child.id === childId}
                aria-current={child.id === childId ? 'page' : undefined}
                data-testid={item.id === 'settings' ? `settings-tab-${child.id}` : undefined}
                render={<Link href={childHref(child)} onClick={onChild(child)} />}
              >
                <span>{child.label}</span>
              </SidebarMenuSubButton>
            </SidebarMenuSubItem>
          ))}
        </SidebarMenuSub>
      ) : null}
    </SidebarMenuItem>
  );
}

function NavSection({ label, items }: { label: string; items: readonly NavGroupItem[] }) {
  return (
    <SidebarGroup className="px-0 py-1">
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((g) => (
            <NavGroup key={g.id} item={g} />
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

/**
 * The dashboard's sidebar: the kit `Sidebar` (adjustable width, icon rail, Sheet
 * below md) composed with the app's nav tree, status and account. All chrome
 * comes from `@digithings/ui/ui`; this file only decides what goes in it.
 */
export default function DashboardSidebar() {
  const { openCommandPalette } = useAppShell();
  const { setOpenMobile } = useSidebar();
  const { canFxHub, fxHubOnlyInvitee } = useFxHubOnlyInvitee();
  const tier = usePlanTier();

  // An fx_hub-only invitee sees FX Hub and a single Account entry (12x single-view contract).
  const workspace = WORKSPACE.filter((g) => (g.href === '/twelve-x' ? canFxHub : !fxHubOnlyInvitee));
  const reference = fxHubOnlyInvitee ? [] : REFERENCE;
  const settings = fxHubOnlyInvitee
    ? { ...settingsGroup(null), label: 'Account', children: [] }
    : settingsGroup(tier);

  return (
    <Sidebar id="app-sidebar-nav" aria-label="Sidebar" data-print-hide>
      <SidebarHeader className="h-10 shrink-0 flex-row items-center justify-between gap-0 border-b border-hair p-0 ps-4 pe-1.5">
        <Link
          href="/"
          onClick={() => setOpenMobile(false)}
          className="inline-flex items-center gap-2.5 font-mono text-[0.75rem] text-ink group-data-[collapsible=icon]:hidden"
        >
          <DashboardMark size={16} />
          <span>
            digi<span className="text-accent">quant</span>
          </span>
        </Link>
        <SidebarTrigger className="max-md:hidden group-data-[collapsible=icon]:mx-auto" />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup className="pb-0">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                tooltip="Search ⌘K"
                variant="outline"
                onClick={() => {
                  setOpenMobile(false);
                  openCommandPalette();
                }}
              >
                <Search />
                <span>Search</span>
                <Kbd className="ms-auto group-data-[collapsible=icon]:hidden">⌘K</Kbd>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>

        <nav aria-label="Primary" className="px-2">
          <NavSection label="Workspace" items={workspace} />
          {reference.length > 0 ? <NavSection label="Reference" items={reference} /> : null}
          {fxHubOnlyInvitee ? null : (
            <SidebarGroup className="px-0 py-1" data-testid="sidebar-bottom-tools">
              <SidebarGroupLabel>Tools</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      tooltip="Gloomberb Terminal"
                      aria-label="Gloomberb Terminal (opens in a new tab)"
                      data-testid="sidebar-gloomberb-link"
                      render={<a href={GLOOMBERB_TERMINAL_URL} target="_blank" rel="noopener noreferrer" />}
                    >
                      <GloomberbMark size={16} />
                      <span>Gloomberb Terminal</span>
                      <ExternalLink className="ms-auto size-3! text-ink-mute group-data-[collapsible=icon]:hidden" aria-hidden />
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )}
          <NavSection label={settings.label} items={[settings]} />
        </nav>
      </SidebarContent>

      <SidebarFooter className="gap-0 p-0">
        <SidebarStatus />
        <SidebarAccount />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
