'use client';

import {
  CalendarDays,
  Clock,
  Cpu,
  FileText,
  GitMerge,
  Landmark,
  ListOrdered,
  Newspaper,
  Scale,
  ShieldCheck,
} from 'lucide-react';

import { LEAN_BAND, SCORE_MAX, STRONG_BAND } from '@/lib/twelve-x/consensus-bar';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';
import type { TwelveXTab } from './context';

/**
 * How it works — the static explainer for the FX research backend. Renders
 * entirely from local content plus the real scoring constants (SCORE_MAX,
 * STRONG_BAND, LEAN_BAND, G10 set) so the explanation cannot drift from the
 * code, and never touches the research feed — it stays readable while the
 * feed is loading, unconfigured, or down.
 */

interface Stage {
  n: number;
  id: string;
  icon: typeof FileText;
  title: string;
  store: string;
  what: string;
  read: string;
  tab: TwelveXTab | null;
  tabLabel: string | null;
}

const STAGES: Stage[] = [
  {
    n: 1,
    id: 'ingest',
    icon: Newspaper,
    title: 'Ingest desk research',
    store: 'fx_research_history',
    what: 'Every sell-side and desk report we receive is read in full and captured as a brief: its central thesis, and — for every currency or pair the analysts actually take a stance on — the direction, conviction, a one-line signal, their rationale, any price targets, the catalysts and risks they flag, and the timeframe the call was made on (short: ≤1 week, medium: ≤4 weeks, or long: ~a quarter), read from the note’s own language. Nothing is summarized away — the original text stays attached to everything derived from it.',
    read: 'Open any brief from the Today tab or from a desk name anywhere in the workspace — the slide-over shows the source note itself.',
    tab: 'today',
    tabLabel: 'Today',
  },
  {
    n: 2,
    id: 'relevance',
    icon: Scale,
    title: 'Score relevance',
    store: 'fx_relevance_ledger',
    what: 'Each report is weighed before it can influence a view, on three factors: how fresh it is (a same-day call outweighs a two-week-old one), how it sits against the event calendar (a call about an event still ahead counts in full; one about an event that already fired is discounted), and how it read on review. Critically, if the same analyst or desk has since published a newer view, the older one steps aside instead of being counted twice. The product is a single relevance weight per report, with a written reason — see Freshness below.',
    read: 'Desk lists in the currency drilldown are ordered by this relevance weight — the reports doing the work rank first, each with its reason.',
    tab: 'consensus',
    tabLabel: 'Consensus',
  },
  {
    n: 3,
    id: 'consensus',
    icon: GitMerge,
    title: 'Build consensus',
    store: 'fx_consensus_snapshot',
    what: `For each of the ${G10_CURRENCIES.length} G10 currencies, views are first grouped by their timeframe into short / medium / long-term buckets, scored within each, then blended into one −${SCORE_MAX}…+${SCORE_MAX} score — alongside its decomposition: agreement between desks, tilt, effective desk count, and the bullish / bearish / neutral / watch split.`,
    read: 'The Consensus tab is this table over time — divergent bars per currency, run-over-run deltas, and the per-currency drilldown for the decomposition.',
    tab: 'consensus',
    tabLabel: 'Consensus',
  },
  {
    n: 4,
    id: 'confluence',
    icon: Landmark,
    title: 'Find confluence',
    store: 'fx_confluence_snapshot',
    what: 'Where independent desks align, a confluence idea is scored from four legs: consensus strength, event alignment, recency, and breadth of desks. Alignment that emerges independently across desks is the strongest signal this system produces.',
    read: 'Ranked confluence signals appear on Today; the drilldown explains each one through the three provenance tiers below.',
    tab: 'today',
    tabLabel: 'Today',
  },
  {
    n: 5,
    id: 'digest',
    icon: FileText,
    title: 'Write the digest',
    store: 'fx_daily_digest',
    what: 'The run closes with a synthesized narrative: the day’s market read, key themes, and what changed since the previous run — with counts of the documents and desks behind it.',
    read: 'The digest brief anchors the Today tab; its key themes are the day’s table of contents.',
    tab: 'today',
    tabLabel: 'Today',
  },
  {
    n: 6,
    id: 'ideas',
    icon: ListOrdered,
    title: 'Rank trade ideas',
    store: 'fx_trade_ideas_snapshot',
    what: 'Finally the run proposes ranked trade ideas — pair, direction, central thesis, levels and targets, the catalyst, and the contributing desks. Rank 1 is the strongest; every idea lists which desks contributed to it.',
    read: 'Today leads with the focal #1 idea; the rest stack beneath it, each opening its full detail.',
    tab: 'today',
    tabLabel: 'Today',
  },
];

const EVENTS_STAGE = {
  icon: CalendarDays,
  title: 'Economic calendar',
  store: 'economic_calendar · fx_events_snapshot',
  what: 'In parallel, a 14-day macro event window is maintained — each event carrying desk opinions and citations, so the calendar reads as research, not just a schedule.',
  read: 'The Events tab shows the window as a list or an intraday timeline; high-impact events are flagged.',
} as const;

/** Every field captured per currency/pair view, extracted at Ingest. */
const BRIEF_FIELDS = [
  { field: 'Thesis', body: "The desk's core argument, in their own terms." },
  { field: 'Currency view', body: 'Direction + conviction + a one-line signal, per currency or pair the note takes a stance on.' },
  { field: 'Rationale', body: 'Why the desk holds that view — their own reasoning, not ours.' },
  { field: 'Targets / levels', body: 'Price levels or ranges the note itself states.' },
  { field: 'Timeframe', body: 'Short (≤1wk) · Medium (≤4wk) · Long (~quarter) — read from the note’s stated or implied horizon.' },
  { field: 'Risk events', body: 'Catalysts the desk flags, matched to the tracked economic calendar by name and date.' },
  { field: 'Positioning', body: 'Crowding, flows, or sentiment the note mentions.' },
] as const;

/** Directions and conviction levels, as extracted per view. */
const VIEW_LEGEND = {
  directions: ['🟢 Bullish', '🔴 Bearish', '⚪ Neutral', '👁 Watch'],
  conviction: 'High · Medium · Low — higher conviction weighs more in the consensus score.',
} as const;

/** How a relevance weight resolves to a state a trader can scan at a glance. */
const FRESHNESS_STATES = [
  { status: 'Active', body: 'Still relevant today — nothing newer has displaced it.' },
  { status: 'Confirmed', body: 'Recent data or events have supported the original call.' },
  { status: 'Superseded', body: 'The same desk has since published a newer view — the old one steps aside so it is never double-counted.' },
  { status: 'Invalidated', body: 'Markets or data have since moved against the view.' },
] as const;

function SectionHeader({
  icon: Icon,
  title,
  meta,
  tone = 'accent',
}: {
  icon: typeof FileText;
  title: string;
  meta?: string;
  tone?: 'accent' | 'warn';
}) {
  return (
    <div className="flex items-center gap-2 border-b border-hair bg-term-bg px-5 py-3">
      <Icon size={14} className={tone === 'warn' ? 'text-warn' : 'text-accent'} aria-hidden />
      <h3 className="text-xs font-semibold uppercase text-ink-mute">{title}</h3>
      {meta ? <span className="ml-auto font-mono text-xs text-ink-mute">{meta}</span> : null}
    </div>
  );
}

/** The consensus scale, drawn from the real band constants. */
function ScaleDiagram() {
  const pct = (v: number) => ((v + SCORE_MAX) / (2 * SCORE_MAX)) * 100;
  const bands = [
    { from: -SCORE_MAX, to: -STRONG_BAND, label: 'Strong bearish', cls: 'bg-warn/30' },
    { from: -STRONG_BAND, to: -LEAN_BAND, label: 'Lean bearish', cls: 'bg-warn/15' },
    { from: -LEAN_BAND, to: LEAN_BAND, label: 'Neutral', cls: 'bg-ink/[0.06]' },
    { from: LEAN_BAND, to: STRONG_BAND, label: 'Lean bullish', cls: 'bg-accent/15' },
    { from: STRONG_BAND, to: SCORE_MAX, label: 'Strong bullish', cls: 'bg-accent/30' },
  ];
  return (
    <div data-testid="hiw-scale" className="px-5 py-4">
      <div className="relative flex h-8 w-full overflow-hidden border border-hair">
        {bands.map((b) => (
          <div
            key={b.label}
            title={b.label}
            className={`${b.cls} h-full border-r border-hair last:border-r-0`}
            style={{ width: `${pct(b.to) - pct(b.from)}%` }}
          />
        ))}
        <div className="absolute inset-y-0 left-1/2 w-px bg-ink/40" aria-hidden />
      </div>
      <div className="mt-2 flex justify-between font-mono text-xs text-ink-mute">
        <span>−{SCORE_MAX}</span>
        <span>−{STRONG_BAND}</span>
        <span>−{LEAN_BAND}</span>
        <span>0</span>
        <span>+{LEAN_BAND}</span>
        <span>+{STRONG_BAND}</span>
        <span>+{SCORE_MAX}</span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-ink-soft">
        Every consensus number lives on this scale. Beyond ±{LEAN_BAND} the desks lean; beyond ±
        {STRONG_BAND} the lean is strong. The score is a weighted aggregate — a single loud desk
        cannot move it the way several independent desks in agreement can.
      </p>
    </div>
  );
}

export default function HowItWorksTab() {
  const { crossLink } = useTwelveX();

  return (
    <div data-testid="twelvex-how-it-works" className="space-y-8">
      {/* One-paragraph orientation */}
      <section className="border-y border-hair">
        <SectionHeader icon={Landmark} title="What this tool is" />
        <div className="px-5 py-4">
          <p className="max-w-3xl text-sm leading-relaxed text-ink-soft">
            The FX Hub reads every FX research note the desks publish, weighs each one for freshness
            and credibility, and distills the whole stack into one question:{' '}
            <span className="text-ink">where do independent desks agree, and how strongly?</span>{' '}
            Each morning it rebuilds the full picture — consensus per currency, confluence across
            desks, a written digest, and ranked trade ideas — with every number traceable back to
            the named desk reports behind it.
          </p>
        </div>
      </section>

      {/* The daily run — numbered flow rail */}
      <section data-testid="hiw-flow" className="border-y border-hair">
        <SectionHeader icon={GitMerge} title="The daily run" meta="six stages, every market day" />
        <ol className="grid divide-y divide-hair md:grid-cols-2 md:divide-y-0 lg:grid-cols-3">
          {STAGES.map((s) => (
            <li key={s.id} className="border-hair p-5 md:border-b lg:[&:nth-child(n+4)]:border-b-0 md:odd:border-r lg:odd:border-r-0 lg:[&:not(:nth-child(3n))]:border-r">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-2xl font-semibold text-accent">{s.n}</span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink">{s.title}</p>
                  <p className="font-mono text-xs text-ink-mute">{s.store}</p>
                </div>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-ink-soft">{s.what}</p>
              <p className="mt-3 text-xs leading-relaxed text-ink-mute">{s.read}</p>
              {s.tab ? (
                <button
                  type="button"
                  onClick={() => crossLink({ kind: 'tab', tab: s.tab as TwelveXTab })}
                  className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                >
                  See it live → {s.tabLabel}
                </button>
              ) : null}
            </li>
          ))}
        </ol>
      </section>

      {/* What's captured per brief */}
      <section className="border-y border-hair">
        <SectionHeader icon={Newspaper} title="What's captured in every brief" meta="one row per currency / pair view" />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <tbody className="divide-y divide-hair">
              {BRIEF_FIELDS.map((f) => (
                <tr key={f.field}>
                  <th scope="row" className="w-40 whitespace-nowrap px-5 py-3 align-top font-mono text-xs font-semibold uppercase text-ink-mute">
                    {f.field}
                  </th>
                  <td className="px-5 py-3 leading-relaxed text-ink-soft">{f.body}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-hair px-5 py-3">
          <span className="font-mono text-xs uppercase text-ink-mute">Directions</span>
          <span className="text-sm text-ink-soft">{VIEW_LEGEND.directions.join('  ·  ')}</span>
        </div>
        <div className="border-t border-hair px-5 py-3">
          <span className="font-mono text-xs uppercase text-ink-mute">Conviction</span>{' '}
          <span className="text-sm text-ink-soft">{VIEW_LEGEND.conviction}</span>
        </div>
      </section>

      {/* Parallel events feed */}
      <section className="border-y border-hair">
        <SectionHeader
          icon={EVENTS_STAGE.icon}
          title={EVENTS_STAGE.title}
          meta={EVENTS_STAGE.store}
          tone="warn"
        />
        <div className="grid gap-4 px-5 py-4 md:grid-cols-2">
          <p className="text-sm leading-relaxed text-ink-soft">{EVENTS_STAGE.what}</p>
          <div>
            <p className="text-xs leading-relaxed text-ink-mute">{EVENTS_STAGE.read}</p>
            <button
              type="button"
              onClick={() => crossLink({ kind: 'tab', tab: 'events' })}
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
            >
              See it live → Events
            </button>
          </div>
        </div>
      </section>

      {/* Reading the scale */}
      <section className="border-y border-hair">
        <SectionHeader icon={Scale} title="Reading the consensus scale" meta={`G10 · −${SCORE_MAX} to +${SCORE_MAX}`} />
        <ScaleDiagram />
      </section>

      {/* Freshness / relevance states */}
      <section className="border-y border-hair">
        <SectionHeader icon={Clock} title="Freshness — why old views step aside" meta="how a view stays (or stops being) relevant" />
        <div className="divide-y divide-hair">
          {FRESHNESS_STATES.map((s) => (
            <div key={s.status} className="grid gap-2 px-5 py-3 md:grid-cols-[10rem_minmax(0,1fr)]">
              <p className="font-mono text-xs font-semibold uppercase text-ink-mute">{s.status}</p>
              <p className="text-sm leading-relaxed text-ink-soft">{s.body}</p>
            </div>
          ))}
        </div>
        <div className="border-t border-hair px-5 py-3">
          <p className="text-xs leading-relaxed text-ink-mute">
            Views that fade count less in the live consensus; very stale views drop off the board
            entirely — the Hub shows the current street, not a pile of old PDFs.
          </p>
        </div>
      </section>

      {/* Models & consistency */}
      <section className="border-y border-hair">
        <SectionHeader icon={Cpu} title="Models & consistency" meta="what reads the research, and why the shape never drifts" />
        <div className="px-5 py-4">
          <p className="max-w-3xl text-sm leading-relaxed text-ink-soft">
            Every note is read by a large language model against a strict schema — the same fields,
            in the same shape, for every desk, every day — and the model grades its own extraction
            against a faithfulness rubric before anything is stored. That consistency is what lets
            today&apos;s board compare cleanly to one from months ago, even as the model doing the
            reading changes. Models run via OpenRouter; the pilot is currently tuned for cost
            efficiency, with a defined upgrade path to a flagship-tier model chosen specifically for
            accuracy on financial documents once this moves past pilot.
          </p>
        </div>
      </section>

      {/* Provenance */}
      <section data-testid="hiw-provenance" className="border-y border-hair">
        <SectionHeader icon={ShieldCheck} title="Why you can trust a number" meta="three tiers, one click deep" />
        <div className="divide-y divide-hair">
          {[
            {
              tier: 'Tier 1 — the score legs',
              body: 'Every confluence idea decomposes into its four legs: how strongly the desks agree, how the event calendar aligns, how fresh the underlying research is, and how many independent desks contribute.',
            },
            {
              tier: 'Tier 2 — the consensus decomposition',
              body: 'Behind each leg sits the full per-currency consensus record: score, confidence, desk agreement, tilt, effective desk count, and the bullish / bearish / neutral / watch split.',
            },
            {
              tier: 'Tier 3 — the named desk reports',
              body: 'And behind that, the actual reports: each supporting desk listed by relevance with its direction, conviction, and the written reason its research was weighted the way it was. The chain ends at a document a human wrote.',
            },
          ].map((t) => (
            <div key={t.tier} className="grid gap-2 px-5 py-4 md:grid-cols-[14rem_minmax(0,1fr)]">
              <p className="font-mono text-xs font-semibold uppercase text-ink-mute">{t.tier}</p>
              <p className="text-sm leading-relaxed text-ink-soft">{t.body}</p>
            </div>
          ))}
        </div>
        <div className="border-t border-hair px-5 py-3">
          <p className="font-mono text-xs text-ink-mute" role="note">
            The FX Hub is a research tool — it reads and weighs desk research; it never executes
            trades. Research that goes stale loses its weight instead of its trace.
          </p>
        </div>
      </section>
    </div>
  );
}
