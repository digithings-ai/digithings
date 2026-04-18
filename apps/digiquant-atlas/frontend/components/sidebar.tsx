'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { ElementType } from 'react';
import { LayoutDashboard, PieChart, BookOpen, ChevronLeft, ChevronRight } from 'lucide-react';
import { AtlasMark } from '@/components/atlas-mark';
import { useAppShell } from '@/components/app-shell-context';
import SidebarSettings from '@/components/sidebar-settings';

interface NavItem {
  href: string;
  label: string;
  icon: ElementType<{ size?: number }>;
}

const NAV: NavItem[] = [
  { href: '/', label: 'Overview', icon: LayoutDashboard },
  { href: '/portfolio', label: 'Portfolio', icon: PieChart },
  { href: '/research', label: 'Research', icon: BookOpen },
];

function routeActive(pathname: string, base: string, href: string): boolean {
  const norm = pathname.replace(/\/+$/, '') || '/';
  if (href === '/') {
    // Only the real home route — not every top-level path (those have one segment too).
    const baseNorm = base.replace(/\/+$/, '');
    if (baseNorm) {
      if (norm === baseNorm) return true;
      if (norm.startsWith(`${baseNorm}/`)) {
        const afterBase = norm.slice(baseNorm.length + 1);
        return afterBase.split('/').filter(Boolean).length === 0;
      }
      return false;
    }
    return norm.split('/').filter(Boolean).length === 0;
  }
  if (href === '/portfolio') {
    return /\/portfolio(\/|$)/.test(pathname) || /\/performance(\/|$)/.test(pathname);
  }
  if (href === '/research') {
    return /\/research(\/|$)/.test(pathname) || /\/library(\/|$)/.test(pathname);
  }
  const candidates = [href, `${base}${href}`, `${href}/`, `${base}${href}/`].filter(
    (p, i, a) => p && a.indexOf(p) === i
  );
  return candidates.some((p) => norm === p || norm.endsWith(p));
}

export default function Sidebar() {
  const pathname = usePathname();
  const base = process.env.NEXT_PUBLIC_BASE_PATH ?? '';
  const { sidebarCollapsed, toggleSidebar, mobileNavOpen, setMobileNavOpen } = useAppShell();

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname, setMobileNavOpen]);

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
        className={`
          bg-bg-glass backdrop-blur-[12px] border-r border-border-subtle
          flex flex-col shrink-0
          fixed top-0 left-0 h-screen z-[1000] transition-all duration-300 ease-out
          w-[260px]
          ${mobileNavOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0 md:relative md:z-auto
          ${sidebarCollapsed ? 'md:w-[72px]' : 'md:w-[260px]'}
        `}
      >
        <div className="border-b border-border-subtle shrink-0 px-6 py-5 min-h-[72px] flex flex-col justify-center">
          <div
            className={`flex items-center justify-between gap-2 w-full ${sidebarCollapsed ? 'md:hidden' : ''}`}
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <AtlasMark className="shrink-0" />
              <span className="text-base font-medium tracking-tight truncate">Atlas</span>
            </div>
            <button
              type="button"
              onClick={toggleSidebar}
              className="hidden md:flex rounded-lg p-2 text-text-muted hover:text-text-primary hover:bg-white/[0.06] border border-border-subtle shrink-0"
              aria-label="Collapse sidebar"
            >
              <ChevronLeft size={18} />
            </button>
          </div>
          <div
            className={`${sidebarCollapsed ? 'hidden md:flex' : 'hidden'} flex-col items-center gap-3 w-full py-1`}
          >
            <AtlasMark className="shrink-0" />
            <button
              type="button"
              onClick={toggleSidebar}
              className="rounded-lg p-2 text-text-muted hover:text-text-primary hover:bg-white/[0.06] border border-border-subtle"
              aria-label="Expand sidebar"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>

        <nav className="flex-1 py-4 flex flex-col">
          {NAV.map(({ href, label, icon: Icon }) => {
            const isActive = routeActive(pathname, base, href);
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setMobileNavOpen(false)}
                title={sidebarCollapsed ? label : undefined}
                className={`
                  flex items-center gap-3 py-3 text-sm font-medium transition-all
                  ${sidebarCollapsed ? 'md:justify-center md:px-3' : 'px-6'}
                  ${
                    isActive
                      ? 'text-text-primary bg-white/[0.04] border-r-2 border-text-primary'
                      : 'text-text-secondary hover:text-text-primary hover:bg-white/[0.03]'
                  }
                `}
              >
                <Icon size={20} className="shrink-0" />
                <span className={sidebarCollapsed ? 'md:sr-only' : ''}>{label}</span>
              </Link>
            );
          })}
        </nav>

        <div
          className={`border-t border-border-subtle mt-auto overflow-visible relative z-10 ${
            sidebarCollapsed ? 'md:px-2 px-6 py-4' : 'px-6 py-4'
          }`}
        >
          <SidebarSettings sidebarCollapsed={sidebarCollapsed} />
        </div>
      </aside>
    </>
  );
}
