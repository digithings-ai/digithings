'use client';

import { useEffect, useMemo, type ElementType } from 'react';
import { useRouter } from 'next/navigation';
import {
  Activity,
  BookMarked,
  Brain,
  FileText,
  GitBranch,
  LayoutDashboard,
  LineChart,
  Newspaper,
  PieChart,
  Search,
  Settings,
  X,
} from 'lucide-react';
import {
  CommandPalette as CommandPaletteShell,
  type CommandPaletteGroup,
} from '@digithings/web';
import { useDashboard } from '@/lib/dashboard-context';
import { useAppShell } from '@/components/app-shell-context';
import { buildPipelineHref, DIGEST_DOCUMENT_KEYS } from '@/lib/pipeline-links';
import { buildDocumentSearchItems } from '@/lib/document-search';
import type { Doc } from '@/lib/types';

export type CmdItem = {
  id: string;
  title: string;
  hint: string;
  href: string;
  icon: ElementType<{ size?: number; className?: string }>;
};

/**
 * Pure item builder (F2). Re-pointed to the locked Pipeline deep-link grammar.
 * Holds the STATIC palette rows only — base nav + thesis + recent-run blocks.
 * Cross-day document hits are query-dependent and are appended by
 * `filterCommandItems` so they never pollute the empty-query view.
 * Exported so it is testable without the React tree.
 */
export function buildCommandItems(data: ReturnType<typeof useDashboard>['data']): CmdItem[] {
  const theses = data?.portfolio?.strategy?.theses ?? [];
  const docs = data?.docs ?? [];
  const base: CmdItem[] = [
    { id: 'go-today', title: 'Brief', hint: "Today's decision & NAV", href: '/', icon: LayoutDashboard },
    {
      id: 'go-holdings',
      title: 'Portfolio — Holdings',
      hint: 'Weights & positions',
      href: '/portfolio?tab=holdings',
      icon: PieChart,
    },
    {
      id: 'go-theses',
      title: 'Portfolio — Theses',
      hint: 'Thesis tracker',
      href: '/portfolio?tab=theses',
      icon: BookMarked,
    },
    {
      id: 'go-perf',
      title: 'Portfolio — Performance',
      hint: 'NAV, comparables & decision quality',
      href: '/portfolio?tab=performance',
      icon: LineChart,
    },
    {
      id: 'go-pipeline',
      title: 'Pipeline — the daily graph',
      hint: 'Research → deliberation → decision',
      href: '/pipeline',
      icon: GitBranch,
    },
    {
      id: 'go-pipeline-read',
      title: 'Pipeline — the read',
      hint: "Today's digest node",
      href: buildPipelineHref({ node: 'digest', stage: 'synthesis' }),
      icon: Newspaper,
    },
    {
      id: 'go-pipeline-delib',
      title: 'Pipeline — deliberations',
      hint: 'PM ⇄ analyst debates',
      href: buildPipelineHref({ stage: 'selection' }),
      icon: Brain,
    },
    {
      id: 'go-system',
      title: 'System',
      hint: 'Run health & how Olympus works',
      href: '/system',
      icon: Activity,
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

  // Recent run dates: up to 5 most recent unique dates with a digest. `path` is
  // the raw `document_key` (see queries.ts) — baseline days publish `digest`,
  // delta days (the majority) publish `digest-delta`; both must match here or
  // this list silently drops every non-baseline day.
  const recentDates = [
    ...new Set(
      docs
        .filter((d) => (DIGEST_DOCUMENT_KEYS as readonly string[]).includes(d.path))
        .map((d) => d.date),
    ),
  ]
    .sort()
    .reverse()
    .slice(0, 5);
  const recentDateItems: CmdItem[] = recentDates.map((date) => ({
    id: `date-${date}`,
    title: `Pipeline — ${date}`,
    hint: 'Jump to that run',
    href: buildPipelineHref({ date, node: 'digest', stage: 'synthesis' }),
    icon: Newspaper,
  }));

  return [...base, ...thesisItems, ...recentDateItems];
}

/**
 * Filter the static command list by query, then append live document hits (Surface 6).
 * Document hits are query-dependent and keyed off `document_key` (`buildDocumentSearchItems`),
 * so a blank query returns the static list verbatim — no doc dump in the empty-query view.
 */
export function filterCommandItems(items: CmdItem[], docs: Doc[], query: string): CmdItem[] {
  const qq = query.trim().toLowerCase();
  if (!qq) return items;
  const staticMatches = items
    .filter(
      (i) =>
        i.title.toLowerCase().includes(qq) ||
        i.hint.toLowerCase().includes(qq) ||
        i.id.toLowerCase().includes(qq)
    )
    .sort((a, b) => {
      const aTitle = a.title.toLowerCase();
      const bTitle = b.title.toLowerCase();
      const aStarts = aTitle.startsWith(qq) ? 0 : aTitle.includes(qq) ? 1 : 2;
      const bStarts = bTitle.startsWith(qq) ? 0 : bTitle.includes(qq) ? 1 : 2;
      return aStarts - bStarts;
    });
  const docItems: CmdItem[] = buildDocumentSearchItems(docs, query).map((d) => ({
    id: d.id,
    title: d.title,
    hint: d.hint,
    href: d.href,
    icon: FileText,
  }));
  return [...staticMatches, ...docItems];
}

/**
 * App-wide ⌘K palette, riding the promoted @digithings/web CommandPalette
 * shell (dress="glass" — olympus's shipped look) since #1548. The shell owns
 * the overlay/portal, keyboard loop and listbox ARIA; this component keeps
 * everything data- and router-shaped: the ⌘K binding (the shell binds no
 * shortcut), the open flag in app-shell context, the item pipeline
 * (buildCommandItems → filterCommandItems per keystroke) and router.push.
 */
export default function CommandPalette() {
  const router = useRouter();
  const { data } = useDashboard();
  const { commandPaletteOpen: open, openCommandPalette, closeCommandPalette } = useAppShell();

  const items = useMemo<CmdItem[]>(() => buildCommandItems(data), [data]);
  const docs = useMemo<Doc[]>(() => data?.docs ?? [], [data]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (open) {
          closeCommandPalette();
        } else {
          openCommandPalette();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, openCommandPalette, closeCommandPalette]);

  // One unlabeled group; the shell re-invokes this per keystroke with its
  // internal query (filtering policy stays app-side, in filterCommandItems).
  const groups = useMemo(
    () =>
      (query: string): CommandPaletteGroup[] => [
        {
          items: filterCommandItems(items, docs, query).map((item) => {
            const Icon = item.icon;
            return {
              id: item.id,
              label: item.title,
              description: item.hint,
              icon: <Icon size={16} aria-hidden />,
              onSelect: () => router.push(item.href),
            };
          }),
        },
      ],
    [items, docs, router]
  );

  return (
    <CommandPaletteShell
      open={open}
      onClose={closeCommandPalette}
      groups={groups}
      dress="glass"
      inputType="search"
      placeholder="Jump to a page, thesis, or document (ticker / segment)…"
      emptyMessage="No matches"
      inputLeading={<Search size={16} className="text-ink-mute shrink-0" aria-hidden />}
      inputTrailing={
        <button
          type="button"
          onClick={closeCommandPalette}
          className="rounded-md p-1.5 text-ink-mute hover:text-ink hover:bg-ink/[0.07]"
          aria-label="Close"
        >
          <X size={16} />
        </button>
      }
    />
  );
}
