/**
 * @vitest-environment happy-dom
 *
 * Deep links into the FX workspace (`?tab=trades`) must light the tab they
 * open. The dashboard ships as a static export, so the prerendered HTML always
 * carries the default tab — and React repairs mismatched *children* while
 * hydrating but not mismatched attributes. Seeding the tab from the URL in a
 * useState initializer therefore rendered the right panel under a strip that
 * still highlighted Today, and the next click lit a second tab.
 *
 * The two render passes below reproduce that exactly: markup built with no
 * query string (the build-time prerender), hydrated against a URL that has one.
 */
import { act, createElement } from 'react';
import { hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const configured = vi.hoisted(() => ({ value: false }));
vi.mock('@/lib/twelve-x/supabase', () => ({ isTwelveXConfigured: () => configured.value }));

/* The feed is stubbed to resolve empty. Most tests stay unconfigured so the
 * effect short-circuits, but the ?view=ideas restore test configures it so the
 * tab-content gate opens; the named imports still have to resolve either way. */
vi.mock('@/lib/twelve-x/fetch', () => {
  const empty = async () => [];
  return {
    computeConsensusDeltaSet: () => ({}),
    getConsensusDivergence: empty,
    getConsensusTimeSeries: empty,
    getEventOpinions: empty,
    getIdeaEval: empty,
    getConsensusEval: empty,
    getIntelligence: empty,
    getIntelligenceWhy: empty,
    getLatestDigest: async () => null,
    getMatrix: empty,
    getTradeIdeaArchive: empty,
    getTradeIdeas: empty,
    getTradeIdeaHistory: empty,
    getTodayBriefs: empty,
    getTodayEvents: empty,
    getUpcomingEvents: empty,
    getBriefs: empty,
  };
});
vi.mock('@/lib/twelve-x/consensus-derive', () => ({
  selectLatestCompleteConsensus: () => [],
}));

const stub = vi.hoisted(
  () => (name: string) => ({
    default: () => createElement('div', { 'data-stub': name }),
  }),
);
vi.mock('./TodayTab', () => stub('today'));
vi.mock('./BriefsIndex', () => stub('briefs'));
vi.mock('./IdeaCardsIndex', () => stub('ideas-index'));
vi.mock('./IdeaPanel', () => ({
  default: (props: { open?: boolean; runDate?: string | null; rank?: number | null }) =>
    createElement('div', {
      'data-stub': 'idea-panel',
      'data-open': String(Boolean(props.open)),
      'data-run': props.runDate ?? '',
      'data-rank': props.rank == null ? '' : String(props.rank),
    }),
}));
vi.mock('./ConsensusTab', () => stub('consensus'));
vi.mock('./EventsTab', () => stub('events'));
vi.mock('./HowItWorksTab', () => stub('how-it-works'));
vi.mock('./MatrixTab', () => stub('matrix'));
vi.mock('./TradesTab', () => stub('trades'));
vi.mock('./TrackRecordTab', () => stub('track-record'));
vi.mock('./BriefPanel', () => stub('brief-panel'));
vi.mock('./TwelveXHeading', () => stub('heading'));
vi.mock('./useWatchlist', () => ({ useWatchlist: () => null }));
vi.mock('@/components/page-skeleton', () => stub('skeleton'));
vi.mock('@digithings/web', () => ({
  EmptyState: () => createElement('div', { 'data-stub': 'empty' }),
}));
vi.mock('@/components/subpage-tab-bar', () => ({
  subpageTabButtonClass: (active: boolean) => (active ? 'tab-on' : 'tab-off'),
  SubpageStickyTabBar: ({ children }: { children?: unknown }) =>
    createElement('div', { 'data-tabs': '1' }, children as never),
}));

import TwelveXClient from './TwelveXClient';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const PATH = '/dashboard/twelve-x/';

/** Prerender with no query string, then hydrate under `search`. */
async function hydrateAt(search: string): Promise<{ container: HTMLDivElement; root: Root }> {
  window.history.replaceState(null, '', PATH);
  const container = document.createElement('div');
  container.innerHTML = renderToString(createElement(TwelveXClient));
  document.body.appendChild(container);

  window.history.replaceState(null, '', `${PATH}${search}`);
  let root!: Root;
  await act(async () => {
    root = hydrateRoot(container, createElement(TwelveXClient));
  });
  // Flush the post-hydration data effect so the gate (loading/error) settles
  // before assertions that depend on the resolved view.
  await act(async () => {});
  return { container, root };
}

function activeTabs(container: HTMLElement): string[] {
  return [...container.querySelectorAll('.tab-on')].map((el) => el.textContent?.trim() ?? '');
}

describe('TwelveXClient deep-link hydration', () => {
  let open: { container: HTMLDivElement; root: Root } | null = null;

  beforeEach(() => {
    open = null;
  });

  afterEach(() => {
    if (open) {
      const { container, root } = open;
      act(() => {
        root.unmount();
      });
      container.remove();
    }
    configured.value = false;
    window.history.replaceState(null, '', PATH);
  });

  it('lights the linked tab, and only that tab', async () => {
    open = await hydrateAt('?tab=trades');
    expect(activeTabs(open.container)).toEqual(['Trades']);
  });

  it('keeps ?tab=track-record resolvable with no tab chrome (hidden scoreboard)', async () => {
    open = await hydrateAt('?tab=track-record');
    expect(activeTabs(open.container)).toEqual([]);
  });

  it('stays on Today with no tab param', async () => {
    open = await hydrateAt('');
    expect(activeTabs(open.container)).toEqual(['Today']);
  });

  it('restores ?view=ideas to the live-ideas index', async () => {
    configured.value = true;
    open = await hydrateAt('?view=ideas');
    expect(open.container.querySelector('[data-stub="ideas-index"]')).not.toBeNull();
    expect(activeTabs(open.container)).toEqual(['Today']);
  });

  it('restores ?idea=&ideaRank= into the open idea panel', async () => {
    open = await hydrateAt('?idea=2026-07-24&ideaRank=2');
    const panel = open.container.querySelector('[data-stub="idea-panel"]');
    expect(panel?.getAttribute('data-open')).toBe('true');
    expect(panel?.getAttribute('data-run')).toBe('2026-07-24');
    expect(panel?.getAttribute('data-rank')).toBe('2');
  });
});
