'use client';

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ElementType,
} from 'react';
import { useRouter } from 'next/navigation';
import {
  Activity,
  BookMarked,
  BookOpen,
  Brain,
  Database,
  LayoutDashboard,
  LineChart,
  Newspaper,
  PieChart,
  Search,
  Settings,
  X,
} from 'lucide-react';
import { useDashboard } from '@/lib/dashboard-context';

type CmdItem = {
  id: string;
  title: string;
  hint: string;
  href: string;
  icon: ElementType<{ size?: number; className?: string }>;
};

export default function CommandPalette() {
  const router = useRouter();
  const { data } = useDashboard();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);
  const selectedIndexRef = useRef(0);

  const items = useMemo<CmdItem[]>(() => {
    const last = data?.portfolio?.meta?.last_updated ?? null;
    const theses = data?.portfolio?.strategy?.theses ?? [];
    const docs = data?.docs ?? [];
    const digestHref =
      last != null
        ? `/research?tab=daily&date=${encodeURIComponent(last)}&docKey=${encodeURIComponent('digest')}`
        : '/research?tab=daily';

    const base: CmdItem[] = [
      { id: 'go-home', title: 'Overview', hint: 'Dashboard home', href: '/', icon: LayoutDashboard },
      {
        id: 'go-alloc',
        title: 'Portfolio — Allocations',
        hint: 'Weights & positions',
        href: '/portfolio?tab=allocations',
        icon: PieChart,
      },
      {
        id: 'go-act',
        title: 'Portfolio — Activity',
        hint: 'Trades & rebalances',
        href: '/portfolio?tab=activity',
        icon: Activity,
      },
      {
        id: 'go-perf',
        title: 'Portfolio — Performance',
        hint: 'NAV, comparables, stats',
        href: '/portfolio?tab=performance',
        icon: LineChart,
      },
      {
        id: 'go-theses',
        title: 'Portfolio — Theses',
        hint: 'Sleeves, thesis book & exploration',
        href: '/portfolio/theses',
        icon: BookMarked,
      },
      {
        id: 'go-intel',
        title: 'Portfolio — Intelligence',
        hint: 'PM artifacts & history calendar',
        href: '/portfolio?tab=analysis',
        icon: Brain,
      },
      {
        id: 'go-digest',
        title: 'Research — Latest digest',
        hint: last ? `Run date ${last}` : 'Daily digest',
        href: digestHref,
        icon: Newspaper,
      },
      {
        id: 'go-research',
        title: 'Research — Daily digest tab',
        hint: 'Browse runs & files',
        href: '/research?tab=daily',
        icon: BookOpen,
      },
      {
        id: 'go-kb',
        title: 'Research — Knowledge base',
        hint: 'Evergreen reference',
        href: '/research?tab=knowledge',
        icon: BookOpen,
      },
      {
        id: 'go-arch',
        title: 'Architecture',
        hint: 'How Atlas is wired',
        href: '/architecture',
        icon: Database,
      },
      {
        id: 'go-settings',
        title: 'Settings',
        hint: 'Theme & shortcuts',
        href: '/settings',
        icon: Settings,
      },
    ];

    const thesisItems: CmdItem[] = theses.map((t) => ({
      id: `thesis-${t.id}`,
      title: `Thesis — ${t.name}`,
      hint: t.id,
      href: `/portfolio/theses/${encodeURIComponent(t.id)}`,
      icon: Brain,
    }));

    // Recent run dates: up to 5 most recent unique dates with a digest
    const recentDates = [...new Set(docs.filter((d) => d.path === 'digest' || d.path === 'Digest').map((d) => d.date))]
      .sort()
      .reverse()
      .slice(0, 5);
    const recentDateItems: CmdItem[] = recentDates.map((date) => ({
      id: `date-${date}`,
      title: `Research — ${date}`,
      hint: 'Jump to run',
      href: `/research?tab=daily&date=${encodeURIComponent(date)}&docKey=${encodeURIComponent('digest')}`,
      icon: Newspaper,
    }));

    return [...base, ...thesisItems, ...recentDateItems];
  }, [data]);

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) return items;
    const matches = items.filter(
      (i) =>
        i.title.toLowerCase().includes(qq) ||
        i.hint.toLowerCase().includes(qq) ||
        i.id.toLowerCase().includes(qq)
    );
    // Sort: title-start matches first, then hint matches, then rest
    return matches.sort((a, b) => {
      const aTitle = a.title.toLowerCase();
      const bTitle = b.title.toLowerCase();
      const aStarts = aTitle.startsWith(qq) ? 0 : aTitle.includes(qq) ? 1 : 2;
      const bStarts = bTitle.startsWith(qq) ? 0 : bTitle.includes(qq) ? 1 : 2;
      return aStarts - bStarts;
    });
  }, [items, q]);

  const filteredRef = useRef(filtered);

  const onNavigate = useCallback(
    (href: string) => {
      router.push(href);
      setOpen(false);
      setQ('');
      setSelectedIndex(0);
    },
    [router]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
        setSelectedIndex(0);
      }
      if (e.key === 'Escape') {
        setOpen(false);
        setQ('');
        setSelectedIndex(0);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useLayoutEffect(() => {
    selectedIndexRef.current = selectedIndex;
  }, [selectedIndex]);

  useLayoutEffect(() => {
    filteredRef.current = filtered;
  }, [filtered]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      const len = filteredRef.current.length;
      if (len === 0) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, len - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const list = filteredRef.current;
        const idx = Math.min(Math.max(0, selectedIndexRef.current), list.length - 1);
        const item = list[idx];
        if (item) onNavigate(item.href);
      } else if (e.key === 'Home') {
        e.preventDefault();
        setSelectedIndex(0);
      } else if (e.key === 'End') {
        e.preventDefault();
        setSelectedIndex(len - 1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onNavigate]);

  useLayoutEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.querySelector(`[data-cmd-index="${selectedIndex}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex, open, filtered]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[2000] flex items-start justify-center pt-[12vh] px-3 sm:px-4" role="dialog" aria-modal="true" aria-label="Command palette">
      <button type="button" className="absolute inset-0 bg-black/75 backdrop-blur-[2px]" onClick={() => setOpen(false)} aria-label="Close" />
      <div className="relative w-full max-w-lg rounded-xl border border-border-subtle bg-[#101010] shadow-2xl shadow-black/50 overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border-subtle px-3 py-2.5">
          <Search size={16} className="text-text-muted shrink-0" aria-hidden />
          <input
            type="search"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setSelectedIndex(0);
            }}
            placeholder="Jump to page, digest, or thesis…"
            className="flex-1 min-w-0 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none py-1.5"
            autoComplete="off"
            autoFocus
            aria-label="Search commands"
          />
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-md p-1.5 text-text-muted hover:text-text-primary hover:bg-white/[0.06]"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        <ul
          ref={listRef}
          className="max-h-[min(52vh,420px)] overflow-y-auto py-1"
          role="listbox"
          aria-label="Commands"
        >
          {filtered.length === 0 ? (
            <li className="px-4 py-8 text-center text-sm text-text-muted">No matches</li>
          ) : (
            filtered.map((item, index) => {
              const Icon = item.icon;
              const active = index === selectedIndex;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    data-cmd-index={index}
                    onClick={() => onNavigate(item.href)}
                    onMouseEnter={() => setSelectedIndex(index)}
                    className={`w-full flex items-start gap-3 px-3 py-2.5 text-left transition-colors ${
                      active
                        ? 'bg-fin-blue/15 ring-1 ring-inset ring-fin-blue/35'
                        : 'hover:bg-white/[0.05]'
                    }`}
                  >
                    <Icon size={16} className="text-fin-blue shrink-0 mt-0.5" aria-hidden />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-text-primary">{item.title}</span>
                      <span className="block text-[11px] text-text-muted truncate">{item.hint}</span>
                    </span>
                  </button>
                </li>
              );
            })
          )}
        </ul>
      </div>
    </div>
  );
}
