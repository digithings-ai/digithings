'use client';

import {
  CalendarDays,
  Check,
  Crosshair,
  FileText,
  LayoutGrid,
  ListOrdered,
  Newspaper,
  Scale,
  ShieldCheck,
  X,
} from 'lucide-react';

import { Button } from '@digithings/ui/ui';
import { PROVENANCES } from '@/lib/twelve-x/trade-levels';
import type { FxLevelProvenance } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';
import type { TwelveXTab } from './context';

/**
 * How it works — the short, fact-locked explainer for the FX Hub. Static
 * content only: it never touches the research feed, so it stays readable
 * while the feed is loading, unconfigured, or down. Copy is locked to the
 * live daily run + level stack (writer lives in the private research repo;
 * the hub only reads snapshots).
 */

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

interface FlowStep {
  n: string;
  icon: typeof FileText;
  title: string;
  body: string;
}

/** The daily run in trader terms — sessions Asia / London / NY, every market day. */
const FLOW: FlowStep[] = [
  {
    n: '01',
    icon: CalendarDays,
    title: 'Calendar',
    body: 'Refresh the macro event window before anything else is read.',
  },
  {
    n: '02',
    icon: Newspaper,
    title: 'Ingest desk research',
    body: 'Read every desk note in full — thesis, direction, conviction, targets, catalysts.',
  },
  {
    n: '03',
    icon: Scale,
    title: 'Score relevance',
    body: 'Weigh each note by freshness, event alignment, and review; newer views displace older ones.',
  },
  {
    n: '04',
    icon: FileText,
    title: 'Digest',
    body: 'Synthesize the day’s market read, key themes, and what changed since the last run.',
  },
  {
    n: '05',
    icon: ListOrdered,
    title: 'Synthesize ideas',
    body: 'Two passes — candidates, then the strategist’s book — into ranked trade ideas.',
  },
  {
    n: '06',
    icon: Crosshair,
    title: 'Attach levels',
    body: 'Deterministic entry / stop / targets per idea, with an optional model polish pass.',
  },
  {
    n: '07',
    icon: LayoutGrid,
    title: 'Daily board',
    body: 'Publish the snapshots the hub reads — board, ideas, briefs, events.',
  },
];

/** Trader-language labels for the provenance chips shown on idea cards. */
const PROVENANCE_LABELS: Record<FxLevelProvenance, string> = {
  broker_quoted: 'broker',
  pmt_bank_trade: 'bank trade',
  pmt_seasonality_target: 'seasonality',
  pmt_position_cluster: 'position book',
  pmt_retail_book: 'retail book',
  computed: 'computed',
  technical: 'technical',
  llm: 'model',
};

const LEVEL_STACK = [
  {
    title: 'Desk levels win when they agree with the idea',
    body: 'Broker quotes, bank trades and bank / seasonality targets — only when they point the same way as the idea’s direction.',
  },
  {
    title: 'Otherwise technical / computed',
    body: 'Structure, ATR and seasonality ladders fill entry, stop and targets when no agreeing desk level exists.',
  },
  {
    title: 'Optional model polish',
    body: 'A model pass may improve placement, but it can only improve — never blank the bracket.',
  },
  {
    title: 'Guard',
    body: 'Every bracket is checked for the correct side, a minimum R:R, and a plausible band; gaps are repaired with computed levels.',
  },
];

const IS_LIST = [
  'A research tool — it reads and weighs desk research',
  'Ideas are synthesized from cited desks, not verbatim tickets',
];

const ISNT_LIST = [
  'It never executes trades',
  'The watchlist is a display filter only — it does not steer the writer',
  'Pair allow / deny and risk-style generation directives are not wired yet',
];

function LiveLink({ tab, label }: { tab: TwelveXTab; label: string }) {
  const { crossLink } = useTwelveX();
  return (
    <Button
      type="button"
      variant="link"
      size="xs"
      onClick={() => crossLink({ kind: 'tab', tab })}
      className="inline-flex h-auto items-center gap-1 p-0 text-xs font-medium text-accent"
    >
      See it live → {label}
    </Button>
  );
}

export default function HowItWorksTab() {
  return (
    <div data-testid="twelvex-how-it-works" className="space-y-8">
      {/* Orientation */}
      <section className="border-y border-hair">
        <SectionHeader icon={LayoutGrid} title="What this tool is" />
        <div className="px-5 py-4">
          <p className="max-w-3xl text-sm leading-relaxed text-ink-soft">
            The FX Hub reads the FX research the desks publish, weighs it for freshness and
            credibility, and distills it into one question:{' '}
            <span className="text-ink">where do independent desks agree, and how strongly?</span>{' '}
            Each run rebuilds the board — ideas with entry / stop / targets, briefs, and events —
            with every number traceable to the named desk reports behind it.
          </p>
        </div>
      </section>

      {/* The daily run — flow strip */}
      <section data-testid="hiw-flow" className="border-y border-hair">
        <SectionHeader icon={Newspaper} title="The daily run" meta="seven steps, every market day" />
        <ol className="grid divide-y divide-hair md:grid-cols-2 md:divide-y-0 lg:grid-cols-4">
          {FLOW.map((s) => (
            <li
              key={s.n}
              className="border-hair p-5 md:border-b lg:[&:nth-child(n+5)]:border-b-0 md:odd:border-r lg:odd:border-r-0 lg:[&:not(:nth-child(4n))]:border-r"
            >
              <div className="flex items-center gap-2">
                <s.icon size={14} className="text-accent" aria-hidden />
                <span className="font-mono text-xs text-ink-mute">{s.n}</span>
              </div>
              <p className="mt-2 text-sm font-semibold text-ink">{s.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-ink-soft">{s.body}</p>
              {s.n === '02' ? (
                <p className="mt-2 font-mono text-xs text-ink-mute">
                  also: retail + positioning + calendar feeds
                </p>
              ) : null}
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap gap-x-6 gap-y-2 border-t border-hair px-5 py-3">
          <LiveLink tab="today" label="Today" />
          <LiveLink tab="trades" label="Trades" />
          <LiveLink tab="events" label="Events" />
        </div>
      </section>

      {/* Levels */}
      <section data-testid="hiw-levels" className="border-y border-hair">
        <SectionHeader icon={Crosshair} title="How entry / stop / targets are set" meta="first plausible wins" />
        <ol className="divide-y divide-hair">
          {LEVEL_STACK.map((l, i) => (
            <li key={l.title} className="grid gap-2 px-5 py-3 md:grid-cols-[2.5rem_minmax(0,1fr)]">
              <span className="font-mono text-sm font-semibold text-accent">{i + 1}</span>
              <div>
                <p className="text-sm font-semibold text-ink">{l.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-ink-soft">{l.body}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="border-t border-hair px-5 py-3">
          <p className="font-mono text-xs uppercase text-ink-mute">Provenance chips on idea cards</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {PROVENANCES.map((p) => (
              <span
                key={p}
                className="border border-hair px-2 py-0.5 font-mono text-xs text-ink-soft"
              >
                {PROVENANCE_LABELS[p]}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* What this is / isn't */}
      <section data-testid="hiw-scope" className="border-y border-hair">
        <SectionHeader icon={ShieldCheck} title="What this is / isn’t" />
        <div className="grid gap-0 md:grid-cols-2 md:divide-x md:divide-hair">
          <ul className="space-y-3 px-5 py-4">
            {IS_LIST.map((t) => (
              <li key={t} className="flex items-start gap-2 text-sm leading-relaxed text-ink-soft">
                <Check size={14} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                {t}
              </li>
            ))}
          </ul>
          <ul className="space-y-3 border-t border-hair px-5 py-4 md:border-t-0">
            {ISNT_LIST.map((t) => (
              <li key={t} className="flex items-start gap-2 text-sm leading-relaxed text-ink-soft">
                <X size={14} className="mt-0.5 shrink-0 text-warn" aria-hidden />
                {t}
              </li>
            ))}
          </ul>
        </div>
        <div className="border-t border-hair px-5 py-3">
          <p className="font-mono text-xs text-ink-mute" role="note">
            Open any brief or idea to walk the source chain back to the named desk reports.
          </p>
        </div>
      </section>
    </div>
  );
}
