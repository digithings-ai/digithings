'use client';

import { useState } from 'react';
import { Settings } from 'lucide-react';
import { usePathname } from 'next/navigation';
import { Dialog, DialogContent } from '@digithings/web/ui';
import { useAppShell } from '@/components/app-shell-context';
import { SettingsContent } from '@/components/settings-content';
import { useDashboard } from '@/lib/dashboard-context';
import { dataSourceHost } from '@/lib/data-source-host';
import { normalizePathname } from '@/lib/pathname';

/**
 * Sidebar settings surface.
 *
 * Wave-2 (#4206): the hand-rolled anchored popover (measured position,
 * scroll/resize listeners, outside-mousedown + window Escape dismissal,
 * manual portal) became a centered modal Dialog (Base UI): scrim, Escape +
 * backdrop dismissal, focus trap, scroll lock, `role="dialog"`.
 *
 * Wave-3 (#4206, T5b): the Dialog is now the canonical kit
 * `@digithings/web/ui` Dialog (T1b: kit ui/* is canonical for every
 * overlapping part) — the owner-blessed centered idiom and 280px sizing are
 * preserved; only the dress source changed (kit tokens vs the retired
 * `ctl-dialog-*` controls skin). The trigger keeps its shipped dress and its
 * `/settings` special case (close nav instead of opening).
 */
export default function SidebarSettings({ sidebarCollapsed }: { sidebarCollapsed: boolean }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { setMobileNavOpen, openCommandPalette } = useAppShell();
  const { data } = useDashboard();
  const meta = data?.portfolio?.meta ?? null;
  const settingsPageActive = normalizePathname(pathname) === '/settings';

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => {
          if (settingsPageActive) {
            setOpen(false);
            setMobileNavOpen(false);
            return;
          }
          setOpen((v) => !v);
        }}
        title="Settings"
        aria-expanded={open}
        aria-haspopup="dialog"
        className={`
          flex items-center gap-3 w-full py-3 text-sm font-medium transition-colors
          text-ink-soft hover:text-ink hover:bg-ink/[0.03]
          ${sidebarCollapsed ? 'md:justify-center md:px-3' : 'px-3'}
          ${open ? 'bg-ink/[0.06] text-ink' : ''}
        `}
      >
        <Settings size={20} className="shrink-0" />
        <span className={sidebarCollapsed ? 'md:sr-only' : ''}>Settings</span>
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
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
              setOpen(false);
              setMobileNavOpen(false);
              openCommandPalette();
            }}
            onNavigate={() => {
              setOpen(false);
              setMobileNavOpen(false);
            }}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
