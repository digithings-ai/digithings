'use client';

import { useEffect, useState, useSyncExternalStore, type ReactNode } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { Button } from '@digithings/ui/ui';
import { useAppShell } from '@/components/app-shell-context';
import { ChatRail } from '@/components/desk/shell/ChatRail';
import { DeskBanner } from '@/components/desk/shell/DeskBanner';
import { DeskRail } from '@/components/desk/shell/DeskRail';
import { PaneGrid, type DeskPaneSlot } from '@/components/desk/shell/PaneGrid';
import { PathChrome } from '@/components/desk/shell/PathChrome';
import SidebarSettings from '@/components/sidebar-settings';
import { useAuth } from '@/lib/auth-context';
import {
  getDeskLayoutServerSnapshot,
  getDeskLayoutSnapshot,
  mergePaneLayout,
  paneColumnsOrDefault,
  subscribeDeskLayout,
  writeDeskLayout,
  type StoredPaneLayout,
} from '@/lib/desk/layout-store';
import {
  formatChromePath,
  locationChrome,
  railForDesk,
} from '@/lib/desk/spine';
import { lockDocumentScroll } from '@/lib/desk/viewport';
import { useFxHubOnlyInvitee } from '@/lib/fx-hub-only';
import type { DeskPaneModel } from '@/components/desk/shell/types';

function seedLayout(slots: readonly DeskPaneSlot[]): StoredPaneLayout[] {
  return slots.map((pane, order) => ({
    id: pane.id,
    columns: paneColumnsOrDefault(pane.columns),
    order,
  }));
}

function pagePane(title: string, chromePath: string, children: ReactNode, state: DeskPaneModel['state']): DeskPaneSlot {
  return {
    id: 'page',
    title,
    chromePath,
    eyebrow: '01',
    state,
    columns: 12,
    children,
  };
}

export default function DeskShell({
  children,
  panes,
}: {
  children: ReactNode;
  panes?: readonly DeskPaneSlot[];
}) {
  const pathname = usePathname() || '/';
  const searchParams = useSearchParams();
  const searchRaw = searchParams?.toString() ?? '';
  const search = searchRaw ? `?${searchRaw}` : '';
  const [hash, setHash] = useState('');
  const { sidebarCollapsed, toggleSidebar, openCommandPalette } = useAppShell();
  const { fxHubOnlyInvitee } = useFxHubOnlyInvitee();
  const { authEnabled, user, signOut } = useAuth();
  const [fullscreenId, setFullscreenId] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    const read = () => setHash(window.location.hash);
    read();
    window.addEventListener('hashchange', read);
    return () => window.removeEventListener('hashchange', read);
  }, [pathname, search]);

  useEffect(() => lockDocumentScroll(document), []);

  useEffect(() => {
    if (!fullscreenId) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      setFullscreenId(null);
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [fullscreenId]);

  const chrome = locationChrome(pathname, search, hash);
  const pathLabel = formatChromePath(chrome.segments);
  const banner = chrome.banner;
  const body = banner ? <DeskBanner banner={banner} /> : children;
  const title = chrome.segments[chrome.segments.length - 1]?.label ?? 'desk';
  const slots: DeskPaneSlot[] =
    panes && panes.length > 0
      ? [...panes]
      : [pagePane(title, pathLabel, body, banner ? 'empty' : 'ready')];

  const savedLayout = useSyncExternalStore(
    subscribeDeskLayout,
    getDeskLayoutSnapshot,
    getDeskLayoutServerSnapshot,
  );
  const seeded = seedLayout(slots);
  const layout = savedLayout
    ? mergePaneLayout(
        seeded.map((pane) => pane.id),
        savedLayout.panes,
      )
    : seeded;

  const commitLayout = (next: StoredPaneLayout[]) => {
    writeDeskLayout({ panes: next }, window.sessionStorage);
  };

  const railWidth = sidebarCollapsed ? '44px' : '208px';
  const chatWidth = fxHubOnlyInvitee ? '0px' : chatOpen ? 'minmax(280px, 360px)' : '44px';

  return (
    <div
      data-desk-shell=""
      data-document-scroll="locked"
      className="grid h-dvh max-h-dvh overflow-hidden bg-bg text-ink"
      style={{
        gridTemplateColumns: `${railWidth} minmax(0, 1fr) ${chatWidth}`,
        gridTemplateRows: '44px minmax(0, 1fr)',
      }}
    >
      <PathChrome
        segments={chrome.segments}
        railCollapsed={sidebarCollapsed}
        onToggleRail={toggleSidebar}
        onSearch={openCommandPalette}
      />
      <DeskRail
        nodes={railForDesk(chrome.deskId, fxHubOnlyInvitee)}
        activeId={chrome.activeRailId}
        collapsed={sidebarCollapsed}
        deskId={chrome.deskId}
        fxHubOnly={fxHubOnlyInvitee}
        footer={
          <>
            {authEnabled && user ? (
              <Button type="button" variant="ghost" size="sm" onClick={() => void signOut()}>
                Sign out
              </Button>
            ) : null}
            <SidebarSettings sidebarCollapsed={sidebarCollapsed} />
          </>
        }
      />
      <div className="min-h-0 min-w-0 overflow-hidden">
        <PaneGrid
          panes={slots}
          layout={layout}
          fullscreenId={fullscreenId}
          onLayout={commitLayout}
          onFullscreen={setFullscreenId}
        />
      </div>
      {fxHubOnlyInvitee ? null : <ChatRail onOpenChange={setChatOpen} />}
    </div>
  );
}

export type { DeskPaneModel };
