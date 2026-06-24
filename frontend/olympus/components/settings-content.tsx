'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Database, Search } from 'lucide-react';
import { useAtlasTheme } from '@/components/theme-provider';
import { AsOfBadge } from '@/components/shared/as-of-badge';
import { normalizePathname } from '@/lib/pathname';

export interface SettingsContentProps {
  /** Tighter spacing for the sidebar popover; slightly fuller for the page. */
  variant?: 'popover' | 'page';
  /** Latest run date (YYYY-MM-DD) and wall-clock UTC timestamp — for the Status card. */
  lastRunDate: string | null;
  lastRunAt: string | null;
  /** Latest run type (baseline | delta) for the Status sub-line; null when unknown. */
  runType: 'baseline' | 'delta' | null;
  /** Build label and friendly data-source host for the About card. */
  version: string;
  dataSourceHost: string | null;
  /** Open the command palette (About card affordance). null disables it (e.g. SSR/test). */
  onOpenPalette?: (() => void) | null;
  onNavigate?: () => void;
}

function systemActive(pathname: string): boolean {
  const path = normalizePathname(pathname);
  return path === '/system' || path.startsWith('/system/');
}

function settingsActive(pathname: string): boolean {
  return normalizePathname(pathname) === '/settings';
}

export function SettingsContent({
  variant = 'popover',
  lastRunDate,
  lastRunAt,
  runType,
  version,
  dataSourceHost,
  onOpenPalette,
  onNavigate,
}: SettingsContentProps) {
  const pathname = usePathname();
  const { theme, setTheme } = useAtlasTheme();
  const sys = systemActive(pathname);
  const settings = settingsActive(pathname);

  return (
    <div className={variant === 'page' ? 'space-y-6' : 'space-y-5'}>
      <div>
        <p className="text-[10px] font-medium text-text-muted mb-2">Status</p>
        {lastRunDate ? (
          <div className="rounded-lg border border-border-subtle bg-bg-secondary/50 px-3 py-2.5 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-text-secondary">Last run</span>
              <AsOfBadge date={lastRunDate} createdAt={lastRunAt} />
            </div>
            <p className="font-mono text-[11px] text-text-muted">
              {formatRunStamp(lastRunDate, lastRunAt)} UTC
              {runType ? <span className="text-text-secondary"> · {runType}</span> : null}
            </p>
          </div>
        ) : (
          <div className="rounded-lg border border-border-subtle bg-bg-secondary/50 px-3 py-2.5">
            <p className="text-xs text-text-muted">No pipeline runs yet</p>
          </div>
        )}
      </div>

      <div>
        <p className="text-[10px] font-medium text-text-muted mb-2">Appearance</p>
        <div className="flex flex-col gap-1.5">
          <div className="grid grid-cols-3 rounded-lg border border-border-subtle overflow-hidden text-xs">
            <button
              type="button"
              aria-pressed={theme === 'auto'}
              onClick={() => setTheme('auto')}
              className={`px-2 py-2 font-medium transition-colors ${
                theme === 'auto' ? 'bg-accent/20 text-accent' : 'text-text-muted hover:bg-white/[0.04]'
              }`}
            >
              Auto
            </button>
            <button
              type="button"
              aria-pressed={theme === 'dark'}
              onClick={() => setTheme('dark')}
              className={`px-2 py-2 font-medium border-l border-border-subtle transition-colors ${
                theme === 'dark' ? 'bg-accent/20 text-accent' : 'text-text-muted hover:bg-white/[0.04]'
              }`}
            >
              Dark
            </button>
            <button
              type="button"
              aria-pressed={theme === 'light'}
              onClick={() => setTheme('light')}
              className={`px-2 py-2 font-medium border-l border-border-subtle transition-colors ${
                theme === 'light' ? 'bg-accent/20 text-accent' : 'text-text-muted hover:bg-white/[0.04]'
              }`}
            >
              Light
            </button>
          </div>
        </div>
      </div>

      <div>
        <p className="text-[10px] font-medium text-text-muted mb-2">About</p>
        <div className="rounded-lg border border-border-subtle bg-bg-secondary/50 divide-y divide-border-subtle">
          <div className="flex items-center justify-between gap-2 px-3 py-2">
            <span className="text-xs text-text-secondary">Build</span>
            <span className="font-mono text-[11px] text-text-muted">{version}</span>
          </div>
          <div className="flex items-center justify-between gap-2 px-3 py-2">
            <span className="text-xs text-text-secondary">Data source</span>
            <span
              className="font-mono text-[11px] text-text-muted truncate max-w-[55%]"
              title={dataSourceHost ?? undefined}
            >
              {dataSourceHost ?? 'not configured'}
            </span>
          </div>
          {onOpenPalette ? (
            <button
              type="button"
              onClick={() => {
                onOpenPalette();
                onNavigate?.();
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-text-secondary hover:bg-white/[0.04] hover:text-text-primary transition-colors"
            >
              <Search size={14} className="shrink-0 text-text-muted" aria-hidden />
              <span>Search</span>
              <kbd className="ml-auto font-mono px-1.5 py-0.5 rounded border border-border-subtle bg-bg-primary text-text-primary">
                ⌘K
              </kbd>
            </button>
          ) : null}
          <Link
            href="/system"
            onClick={onNavigate}
            className={`flex items-center gap-2 px-3 py-2 text-xs font-medium transition-colors ${
              sys ? 'text-accent' : 'text-text-secondary hover:bg-white/[0.04] hover:text-text-primary'
            }`}
          >
            <Database size={14} className="shrink-0" aria-hidden />
            <span>How it works</span>
          </Link>
        </div>
        {!settings ? (
          <Link
            href="/settings"
            onClick={onNavigate}
            className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-text-secondary border border-border-subtle hover:bg-white/[0.04] hover:text-text-primary transition-colors"
          >
            All settings
          </Link>
        ) : null}
      </div>
    </div>
  );
}

/** "2026-06-23" + "2026-06-23T16:13:04Z" → "Jun 23, 16:13". Date-only when no timestamp. */
function formatRunStamp(date: string, createdAt: string | null): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const dm = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const day = dm ? `${months[Number(dm[2]) - 1] ?? dm[2]} ${Number(dm[3])}` : date;
  if (!createdAt) return day;
  const ts = Date.parse(createdAt);
  if (Number.isNaN(ts)) return day;
  const d = new Date(ts);
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${day}, ${hh}:${mm}`;
}
