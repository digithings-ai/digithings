'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Database, Keyboard } from 'lucide-react';
import { useAtlasTheme } from '@/components/theme-provider';

function architectureActive(pathname: string): boolean {
  return /\/architecture(\/|$)/.test(pathname);
}

export function SettingsContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { theme, setTheme } = useAtlasTheme();
  const arch = architectureActive(pathname);

  return (
    <div className="space-y-5">
      <div>
        <p className="text-[10px] font-medium text-text-muted mb-2">Docs</p>
        <Link
          href="/architecture"
          onClick={onNavigate}
          className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors border ${
            arch
              ? 'border-fin-blue/40 bg-fin-blue/10 text-fin-blue'
              : 'border-border-subtle text-text-secondary hover:bg-white/[0.04] hover:text-text-primary'
          }`}
        >
          <Database size={16} className="shrink-0" />
          Architecture
        </Link>
        {pathname !== '/settings' ? (
          <Link
            href="/settings"
            onClick={onNavigate}
            className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-text-secondary border border-border-subtle hover:bg-white/[0.04] hover:text-text-primary transition-colors"
          >
            All settings
          </Link>
        ) : null}
      </div>

      <div>
        <p className="text-[10px] font-medium text-text-muted mb-2">Appearance</p>
        <div className="flex flex-col gap-1.5">
          <div className="grid grid-cols-3 rounded-lg border border-border-subtle overflow-hidden text-xs">
            <button
              type="button"
              onClick={() => setTheme('auto')}
              className={`px-2 py-2 font-medium transition-colors ${
                theme === 'auto' ? 'bg-fin-blue/20 text-fin-blue' : 'text-text-muted hover:bg-white/[0.04]'
              }`}
            >
              Auto
            </button>
            <button
              type="button"
              onClick={() => setTheme('dark')}
              className={`px-2 py-2 font-medium border-l border-border-subtle transition-colors ${
                theme === 'dark' ? 'bg-fin-blue/20 text-fin-blue' : 'text-text-muted hover:bg-white/[0.04]'
              }`}
            >
              Dark
            </button>
            <button
              type="button"
              onClick={() => setTheme('light')}
              className={`px-2 py-2 font-medium border-l border-border-subtle transition-colors ${
                theme === 'light' ? 'bg-fin-blue/20 text-fin-blue' : 'text-text-muted hover:bg-white/[0.04]'
              }`}
            >
              Light
            </button>
          </div>
        </div>
      </div>

      <div>
        <p className="text-[10px] font-medium text-text-muted mb-2">Shortcuts</p>
        <div className="flex items-center gap-2 rounded-lg border border-border-subtle bg-bg-secondary/50 px-3 py-2 text-xs text-text-secondary">
          <Keyboard size={14} className="shrink-0 text-text-muted" aria-hidden />
          <kbd className="font-mono px-1.5 py-0.5 rounded border border-border-subtle bg-bg-primary text-text-primary">
            ⌘K
          </kbd>
        </div>
      </div>
    </div>
  );
}
