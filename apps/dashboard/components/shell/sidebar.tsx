'use client';

import { Suspense, useEffect, type MouseEvent } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
} from 'lucide-react';
import { GLOOMBERB_TERMINAL_URL } from '@digithings/ui';
import { Button, Kbd, Tooltip, TooltipContent, TooltipTrigger } from '@digithings/ui/ui';
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

const ROW =
  'flex h-7 max-md:h-9 items-center gap-2 border-s-2 ps-2 pe-2 font-mono text-[0.78rem] rounded-none outline-none transition-colors focus-visible:ring-1 focus-visible:ring-ring/50';
const IDLE = 'border-s-transparent text-ink-soft hover:bg-accent-weak hover:text-ink';
const ACTIVE = 'border-s-accent bg-accent-weak text-ink';
const LABEL = 'px-2 pt-3 pb-1 font-mono text-[0.68rem] uppercase tracking-[0.12em] text-ink-mute';

/** Same-pathname child links flip URL state in place (no fetch, no scroll) and tell pages. */
function useChildClick(path: string, onNavigate?: () => void) {
  return (child: NavChild) => (e: MouseEvent<HTMLAnchorElement>) => {
    onNavigate?.();
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

function GroupItem({
  item,
  collapsed,
  onNavigate,
}: {
  item: NavGroupItem;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const { path, search, hash } = useNavActive();
  const { openGroups, toggleGroup } = useAppShell();
  const active = ownsPath(item, path);
  const childId = activeChildId(item, path, search, hash);
  const hasChildren = item.children.length > 0;
  const open = hasChildren && (active || openGroups.includes(item.id));
  const childClick = useChildClick(path, onNavigate);
  const Icon = item.icon;
  const parentActive = active && !hasChildren ? true : active;

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <Link
              href={item.href}
              aria-label={item.label}
              aria-current={active ? 'page' : undefined}
              onClick={onNavigate}
              className={`${ROW} justify-center ps-0 pe-0 ${active ? ACTIVE : IDLE}`}
            />
          }
        >
          <Icon className="size-4" aria-hidden />
        </TooltipTrigger>
        <TooltipContent side="right" hideArrow>
          {item.label}
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <div>
      <div className="flex items-center">
        <Link
          href={item.href}
          aria-current={active && !childId ? 'page' : active ? 'true' : undefined}
          onClick={onNavigate}
          className={`${ROW} min-w-0 flex-1 ${parentActive ? ACTIVE : IDLE}`}
        >
          <Icon className="size-4 shrink-0" aria-hidden />
          <span className="truncate">{item.label}</span>
        </Link>
        {hasChildren ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-expanded={open}
            aria-label={`${open ? 'Collapse' : 'Expand'} ${item.label}`}
            onClick={() => toggleGroup(item.id)}
            disabled={active}
          >
            {open ? <ChevronDown /> : <ChevronRight />}
          </Button>
        ) : null}
      </div>
      {open ? (
        <ul className="m-0 list-none p-0">
          {item.children.map((child) => {
            const current = child.id === childId;
            return (
              <li key={child.id}>
                <Link
                  href={childHref(child)}
                  aria-current={current ? 'page' : undefined}
                  onClick={childClick(child)}
                  data-testid={item.id === 'settings' ? `settings-tab-${child.id}` : undefined}
                  className={`${ROW} h-6 max-md:h-9 ps-8 text-[0.74rem] ${current ? ACTIVE : IDLE}`}
                >
                  <span className="truncate">{child.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

function SearchButton({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const { openCommandPalette } = useAppShell();
  const open = () => {
    onNavigate?.();
    openCommandPalette();
  };
  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger
          render={<Button type="button" variant="ghost" size="icon" aria-label="Search" onClick={open} />}
        >
          <Search />
        </TooltipTrigger>
        <TooltipContent side="right" hideArrow>
          Search ⌘K
        </TooltipContent>
      </Tooltip>
    );
  }
  return (
    <Button type="button" variant="outline" size="sm" className="w-full justify-between" onClick={open}>
      <span className="inline-flex items-center gap-2">
        <Search />
        Search
      </span>
      <Kbd>⌘K</Kbd>
    </Button>
  );
}

/** Nav tree, tools, status and account — shared by the desktop aside and the mobile sheet. */
export function SidebarBody({
  forceExpanded = false,
  onNavigate,
}: {
  forceExpanded?: boolean;
  onNavigate?: () => void;
}) {
  const { sidebarCollapsed, toggleSidebar } = useAppShell();
  const { canFxHub, fxHubOnlyInvitee } = useFxHubOnlyInvitee();
  const tier = usePlanTier();
  const collapsed = sidebarCollapsed && !forceExpanded;

  // An fx_hub-only invitee sees FX Hub and a single Account entry (12x single-view contract).
  const workspace = WORKSPACE.filter((g) => (g.href === '/twelve-x' ? canFxHub : !fxHubOnlyInvitee));
  const reference = fxHubOnlyInvitee ? [] : REFERENCE;
  const settings = fxHubOnlyInvitee
    ? { ...settingsGroup(null), label: 'Account', children: [] }
    : settingsGroup(tier);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        className={`flex h-10 shrink-0 items-center border-b border-hair ${collapsed ? 'justify-center' : 'justify-between ps-3 pe-1'}`}
      >
        {collapsed ? null : (
          <Link href="/" onClick={onNavigate} className="inline-flex items-center gap-2 font-mono text-[0.8rem] text-ink">
            <DashboardMark />
            <span>
              digi<span className="text-accent">quant</span>
            </span>
          </Link>
        )}
        {forceExpanded ? null : (
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                  aria-expanded={!collapsed}
                  onClick={toggleSidebar}
                />
              }
            >
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            </TooltipTrigger>
            <TooltipContent side="right" hideArrow>
              {collapsed ? 'Expand' : 'Collapse'} <Kbd>⌘B</Kbd>
            </TooltipContent>
          </Tooltip>
        )}
      </div>

      <div className={collapsed ? 'flex justify-center p-1.5' : 'p-2'}>
        <SearchButton collapsed={collapsed} onNavigate={onNavigate} />
      </div>

      <nav aria-label="Primary" className="min-h-0 flex-1 overflow-y-auto pb-2">
        {collapsed ? null : <div className={LABEL}>Workspace</div>}
        {workspace.map((g) => (
          <GroupItem key={g.id} item={g} collapsed={collapsed} onNavigate={onNavigate} />
        ))}
        {reference.length > 0 ? (
          <>
            {collapsed ? null : <div className={LABEL}>Reference</div>}
            {reference.map((g) => (
              <GroupItem key={g.id} item={g} collapsed={collapsed} onNavigate={onNavigate} />
            ))}
          </>
        ) : null}
        {fxHubOnlyInvitee ? null : (
          <div data-testid="sidebar-bottom-tools">
            {collapsed ? null : <div className={LABEL}>Tools</div>}
            <a
              href={GLOOMBERB_TERMINAL_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Gloomberb Terminal (opens in a new tab)"
              data-testid="sidebar-gloomberb-link"
              className={`${ROW} ${IDLE} ${collapsed ? 'justify-center ps-0 pe-0' : ''}`}
            >
              <GloomberbMark />
              {collapsed ? null : (
                <>
                  <span className="truncate">Gloomberb Terminal</span>
                  <ExternalLink className="ms-auto size-3 shrink-0 text-ink-mute" aria-hidden />
                </>
              )}
            </a>
          </div>
        )}
        {collapsed ? null : <div className={LABEL}>{settings.label}</div>}
        <GroupItem item={settings} collapsed={collapsed} onNavigate={onNavigate} />
      </nav>

      <SidebarStatus collapsed={collapsed} />
      <SidebarAccount collapsed={collapsed} />
    </div>
  );
}

function SidebarInner() {
  const { sidebarCollapsed, toggleSidebar } = useAppShell();
  // Cmd/Ctrl+B collapses; '/' opens the palette (both ignored while typing).
  const { openCommandPalette } = useAppShell();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = !!t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || !!t.closest('[role="dialog"]'));
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        toggleSidebar();
      } else if (e.key === '/' && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        openCommandPalette();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggleSidebar, openCommandPalette]);

  return (
    <aside
      id="app-sidebar-nav"
      aria-label="Sidebar"
      data-print-hide
      data-collapsed={sidebarCollapsed ? '1' : '0'}
      className={`sticky top-0 hidden h-dvh shrink-0 border-e border-hair bg-surface md:block ${
        sidebarCollapsed ? 'w-14' : 'w-60'
      }`}
    >
      <SidebarBody />
    </aside>
  );
}

/** Desktop sidebar. Suspense fallback is an empty aside of the same width so layout never jumps. */
export default function Sidebar() {
  usePathname();
  return (
    <Suspense
      fallback={<aside aria-label="Sidebar" className="hidden h-dvh w-60 shrink-0 border-e border-hair bg-surface md:block" />}
    >
      <SidebarInner />
    </Suspense>
  );
}
