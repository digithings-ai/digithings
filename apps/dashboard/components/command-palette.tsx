'use client';

import { useCallback, useEffect, useMemo, useState, type ElementType } from 'react';
import { useRouter } from 'next/navigation';
import {
  BookMarked,
  Brain,
  FileText,
  GitBranch,
  Globe,
  LayoutDashboard,
  Library,
  LineChart,
  Newspaper,
  PieChart,
  Scale,
  ScrollText,
  Search,
  Settings,
  Tag,
  Users,
  X,
} from 'lucide-react';
import {
  CommandPalette as CommandPaletteShell,
  type CommandPaletteGroup,
} from '@digithings/ui';
import { Button } from '@digithings/ui/ui';
import { useDashboard } from '@/lib/dashboard-context';
import { useAppShell } from '@/components/app-shell-context';
import { buildPipelineHref, DIGEST_DOCUMENT_KEYS } from '@/lib/pipeline-links';
import { buildDocumentSearchItems } from '@/lib/document-search';
import { fetchAllTickers } from '@/lib/queries';
import { thesisDetailHref } from '@/lib/portfolio-url-state';
import { useFxHubOnlyInvitee } from '@/lib/fx-hub-only';
import { getBriefs, getTradeIdeaArchive } from '@/lib/twelve-x/fetch';
import type { FxBriefRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';
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
    { id: 'go-today', title: 'Brief', hint: "Today's decision & performance", href: '/', icon: LayoutDashboard },
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
      title: 'Portfolio — Tearsheet',
      hint: 'Returns & position performance',
      href: '/portfolio/performance',
      icon: LineChart,
    },
    {
      id: 'go-ledger',
      title: 'Portfolio — Ledger',
      hint: 'Position-event activity',
      href: '/portfolio/ledger',
      icon: ScrollText,
    },
    {
      id: 'go-attribution',
      title: 'Portfolio — Attribution',
      hint: 'Position decomposition & recommendation quality',
      href: '/portfolio/attribution',
      icon: Scale,
    },
    {
      id: 'go-house',
      title: 'Corpus · Book · Profile',
      hint: 'House identity chrome (read-only)',
      href: '/house?tab=corpus',
      icon: Library,
    },
    {
      id: 'go-pipeline',
      title: 'Pipeline — the daily graph',
      hint: 'Graph, artifacts & run health',
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
      id: 'go-fx',
      title: 'FX Hub',
      hint: 'Desk consensus, matrix & events',
      href: '/twelve-x',
      icon: Globe,
    },
    {
      id: 'go-fx-how',
      title: 'FX Hub — how it works',
      hint: 'The research pipeline, explained',
      href: '/twelve-x?tab=how-it-works',
      icon: Globe,
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
    href: thesisDetailHref(t.id),
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
 * "Tickers" group (#1562 PR2) — one row per known ticker → the ticker dossier
 * (`/portfolio/tickers?ticker=`). `tickers` is the live `fetchAllTickers()`
 * union (positions + decision_log + analyst docs + analyst_coverage); pure so
 * it is testable without the React tree, matching `buildCommandItems`.
 */
export function buildTickerCommandItems(tickers: string[]): CmdItem[] {
  return tickers.map((t) => ({
    id: `ticker-${t}`,
    title: t,
    hint: 'Ticker dossier',
    href: `/portfolio/tickers?ticker=${encodeURIComponent(t)}`,
    icon: Tag,
  }));
}

/**
 * FX-Hub-only search rows (12x single view) — briefs and trade ideas from the
 * FX research tables, plus one row per broker (the matrix is the broker
 * surface). Every href stays inside `/twelve-x`; no DiGiQuant paths.
 */
export function buildFxHubSearchItems(
  briefs: FxBriefRow[],
  ideas: FxTradeIdeaRow[],
): CmdItem[] {
  const brokers = new Map<string, string>();
  for (const brief of briefs) {
    const name = brief.broker_name?.trim();
    if (!name) continue;
    const key = name.toLowerCase();
    if (!brokers.has(key)) brokers.set(key, name);
  }
  const brokerItems: CmdItem[] = [...brokers.entries()].map(([key, name]) => ({
    id: `fx-broker-${key.replace(/[^a-z0-9]+/g, '-')}`,
    title: name,
    hint: 'Broker — desk profile in the research matrix',
    href: '/twelve-x?tab=matrix',
    icon: Users,
  }));
  const briefItems: CmdItem[] = briefs.map((brief) => ({
    id: `fx-brief-${brief.run_date}-${brief.source_file}`,
    title:
      brief.document_title?.trim() || brief.broker_name?.trim() || brief.source_file,
    hint: `Brief · ${brief.broker_name?.trim() || 'unknown broker'} · ${brief.run_date}`,
    href: `/twelve-x?brief=${encodeURIComponent(brief.source_file)}&briefDate=${encodeURIComponent(brief.run_date)}`,
    icon: FileText,
  }));
  const ideaItems: CmdItem[] = ideas.slice(0, 100).map((idea) => ({
    id: `fx-idea-${idea.run_date}-${idea.rank}`,
    title: idea.title?.trim() || `${idea.pair} ${idea.direction}`,
    hint: `Trade idea · ${idea.pair} · ${idea.run_date}`,
    href: '/twelve-x?tab=trades',
    icon: Scale,
  }));
  return [...briefItems, ...ideaItems, ...brokerItems];
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
 * App-wide ⌘K palette, riding the promoted @digithings/ui CommandPalette
 * shell (dress="glass" — API name; overlay chrome, not a glass surface) since #1548. The shell owns
 * the overlay/portal, keyboard loop and listbox ARIA; this component keeps
 * everything data- and router-shaped: the ⌘K binding (the shell binds no
 * shortcut), the open flag in app-shell context, the item pipeline
 * (buildCommandItems → filterCommandItems per keystroke) and router.push.
 */
export default function CommandPalette() {
  const router = useRouter();
  const { data } = useDashboard();
  const { commandPaletteOpen: open, openCommandPalette, closeCommandPalette } = useAppShell();
  const { canFxHub, fxHubOnlyInvitee } = useFxHubOnlyInvitee();

  const items = useMemo<CmdItem[]>(() => {
    const all = buildCommandItems(data);
    if (fxHubOnlyInvitee) {
      // 12x single-view contract: only FX Hub (+ account settings) is reachable.
      return all.filter(
        (i) =>
          i.id === 'go-fx' || i.id === 'go-fx-how' || i.id === 'go-settings',
      );
    }
    if (canFxHub) return all;
    return all.filter((i) => i.id !== 'go-fx' && i.id !== 'go-fx-how');
  }, [data, canFxHub, fxHubOnlyInvitee]);
  const docs = useMemo<Doc[]>(
    () => (fxHubOnlyInvitee ? [] : data?.docs ?? []),
    [data, fxHubOnlyInvitee]
  );

  // Live ticker union (#1562 PR2) — fetched once on mount, independent of the
  // dashboard context (positions alone would miss decision_log/analyst-only
  // tickers). Fail-soft: an empty list just omits the Tickers group.
  const [tickers, setTickers] = useState<string[]>([]);
  useEffect(() => {
    if (fxHubOnlyInvitee) return;
    let alive = true;
    fetchAllTickers()
      .then((t) => {
        if (alive) setTickers(t);
      })
      .catch(() => {
        if (alive) setTickers([]);
      });
    return () => {
      alive = false;
    };
  }, [fxHubOnlyInvitee]);
  const tickerItems = useMemo<CmdItem[]>(
    () => (fxHubOnlyInvitee ? [] : buildTickerCommandItems(tickers)),
    [fxHubOnlyInvitee, tickers]
  );

  // FX-Hub-only search sources (briefs, brokers via briefs, trade ideas). Loaded
  // when the 12x single view mounts so it keeps its own searchable content.
  // Fail-soft: an empty source list simply omits the FX Hub group.
  const [fxSources, setFxSources] = useState<{
    briefs: FxBriefRow[];
    ideas: FxTradeIdeaRow[];
  }>({ briefs: [], ideas: [] });
  useEffect(() => {
    if (!fxHubOnlyInvitee) return;
    let alive = true;
    Promise.all([
      getBriefs(30).catch(() => [] as FxBriefRow[]),
      getTradeIdeaArchive().catch(() => [] as FxTradeIdeaRow[]),
    ]).then(([briefs, ideas]) => {
      if (alive) setFxSources({ briefs, ideas });
    });
    return () => {
      alive = false;
    };
  }, [fxHubOnlyInvitee]);
  const fxItems = useMemo<CmdItem[]>(
    () => buildFxHubSearchItems(fxSources.briefs, fxSources.ideas),
    [fxSources]
  );

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

  const toOption = useCallback(
    (item: CmdItem) => {
      const Icon = item.icon;
      return {
        id: item.id,
        label: item.title,
        description: item.hint,
        icon: <Icon size={16} aria-hidden />,
        onSelect: () => router.push(item.href),
      };
    },
    [router]
  );

  // The base group stays unlabeled (the shell re-invokes this per keystroke with
  // its internal query; filtering policy stays app-side, in filterCommandItems).
  // The Tickers group (#1562 PR2) is labeled and appended only when it has
  // matches — `filterCommandItems(tickerItems, [], query)` reuses the same
  // substring/starts-with ranking with no document hits mixed in (docs=[]).
  // The FX Hub group (12x single view) follows the same contract: query-only,
  // so the empty view never dumps the brief/idea archive.
  const groups = useMemo(
    () =>
      (query: string): CommandPaletteGroup[] => {
        const tickerMatches = filterCommandItems(tickerItems, [], query);
        const fxMatches =
          fxHubOnlyInvitee && query.trim()
            ? filterCommandItems(fxItems, [], query)
            : [];
        return [
          { items: filterCommandItems(items, docs, query).map(toOption) },
          ...(fxMatches.length > 0
            ? [{ id: 'fx-hub', label: 'FX Hub', items: fxMatches.map(toOption) }]
            : []),
          ...(tickerMatches.length > 0
            ? [{ id: 'tickers', label: 'Tickers', items: tickerMatches.map(toOption) }]
            : []),
        ];
      },
    [items, docs, fxHubOnlyInvitee, fxItems, tickerItems, toOption]
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
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={closeCommandPalette}
          className="text-ink-mute hover:bg-ink/[0.07] hover:text-ink"
          aria-label="Close"
        >
          <X size={16} />
        </Button>
      }
    />
  );
}
