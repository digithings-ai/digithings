'use client';

import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type {
  IntelligenceWhyComponents,
  IntelligenceWhyDesk,
  IntelligenceWhyItem,
} from '@/lib/twelve-x/types';
import { scoreColorClass, scoreLabel } from '@/lib/twelve-x/consensus-bar';
import { ConsensusScoreBar } from './ConsensusScoreBars';

/* ------------------------------------------------------------------ *
 * Tier 1 — score waterfall (PURE, exported for unit test)
 * ------------------------------------------------------------------ */

/** One leg of the confluence-score waterfall. */
export interface WaterfallLeg {
  /** Display name of the leg. */
  label: string;
  /** The fixed score weight (0.50 / 0.30 / 0.20). */
  weight: number;
  /** The leg's [0,1] input (event leg = event_alignment × recency). */
  input: number;
  /** weight × input — the leg's additive contribution to the score. */
  contribution: number;
}

export interface Waterfall {
  legs: WaterfallLeg[];
  /** Sum of the three leg contributions — the reconstructed confluence score. */
  total: number;
}

/**
 * PURE — decompose a confluence idea's score into its three weighted legs:
 *   `0.50·consensus_strength + 0.30·(event_alignment·recency) + 0.20·breadth`.
 * The event leg's input is the product `event_alignment × recency`, so the leg
 * contribution stays `weight × input`. `total` is the sum of contributions.
 */
export function whyWaterfall(c: IntelligenceWhyComponents): Waterfall {
  const legs: WaterfallLeg[] = [
    {
      label: 'Consensus',
      weight: 0.5,
      input: c.consensus_strength,
      contribution: 0.5 * c.consensus_strength,
    },
    {
      label: 'Event',
      weight: 0.3,
      input: c.event_alignment * c.recency,
      contribution: 0.3 * c.event_alignment * c.recency,
    },
    {
      label: 'Breadth',
      weight: 0.2,
      input: c.breadth,
      contribution: 0.2 * c.breadth,
    },
  ];
  const total = legs.reduce((s, l) => s + l.contribution, 0);
  return { legs, total };
}

/* ------------------------------------------------------------------ *
 * presentational helpers
 * ------------------------------------------------------------------ */

/** A human "≤ today / N days" label for the catalyst distance. */
function recencyLabel(days: number | null): string {
  if (days == null) return 'n/a';
  if (days <= 0) return '≤ today';
  return days === 1 ? '1 day' : `${days} days`;
}

/** The 0.50/0.30/0.20 leg-bar colors (consensus / event / breadth). */
const LEG_COLOR = ['#3B82F6', '#6db6ff', '#8B5CF6'] as const;

/** Tier-2 split-bar segments, in the spec's order (Bull / Neutral / Watch / Bear). */
const SPLIT_SEGMENTS = [
  { key: 'bullish_pct', label: 'Bull', color: 'rgba(63,185,132,0.75)' },
  { key: 'neutral_pct', label: 'Neutral', color: 'rgba(148,163,184,0.6)' },
  { key: 'watch_pct', label: 'Watch', color: 'rgba(224,179,65,0.7)' },
  { key: 'bearish_pct', label: 'Bear', color: 'rgba(224,101,75,0.75)' },
] as const;

/** classification → badge color classes (active/confirmed/invalidated/superseded). */
function classificationClass(cls: string): string {
  switch (cls.trim().toLowerCase()) {
    case 'active':
      return 'text-fin-blue border-fin-blue/50 bg-fin-blue/10';
    case 'confirmed':
      return 'text-fin-green border-fin-green/50 bg-fin-green/10';
    case 'invalidated':
      return 'text-fin-red border-fin-red/50 bg-fin-red/10';
    case 'superseded':
      return 'text-fin-amber border-fin-amber/50 bg-fin-amber/10';
    default:
      return 'text-text-muted border-border-subtle bg-white/[0.04]';
  }
}

/** A clamped [0,1] number for bar fills. */
function clamp01(v: number): number {
  return Math.max(0, Math.min(1, Number.isFinite(v) ? v : 0));
}

/** A whole-percent figure from a [0,1] OR [0,100] value (the *_pct contract is %). */
function pct(v: number): number {
  return Math.max(0, Math.round(Number.isFinite(v) ? v : 0));
}

/* ------------------------------------------------------------------ *
 * Tiers
 * ------------------------------------------------------------------ */

function TierOne({ components }: { components: IntelligenceWhyComponents }) {
  const wf = whyWaterfall(components);
  // Each leg's track is its OWN contribution against the leg's max weight, so a
  // strong leg reads as a near-full track (matches the demo's wf-fill recipe).
  const legMax = [0.5, 0.3, 0.2];
  return (
    <div className="mt-4">
      <h4 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        Tier 1 — how it scored
      </h4>
      <div className="space-y-1.5">
        {wf.legs.map((leg, i) => (
          <div key={leg.label} className="flex items-center gap-2.5">
            <span className="w-44 shrink-0 text-[11.5px] text-text-secondary">
              {leg.label}{' '}
              <span className="font-mono tabular-nums text-text-muted">
                {leg.weight.toFixed(2)} × {leg.input.toFixed(2)}
              </span>
            </span>
            <span className="relative h-3 min-w-[80px] flex-1 overflow-hidden rounded-sm bg-white/[0.05]">
              <span
                className="absolute inset-y-0 left-0 rounded-sm"
                style={{
                  width: `${(clamp01(leg.contribution / legMax[i]) * 100).toFixed(1)}%`,
                  backgroundColor: LEG_COLOR[i],
                }}
              />
            </span>
            <span className="w-14 text-right font-mono text-xs tabular-nums text-text-secondary">
              {leg.contribution.toFixed(3)}
            </span>
          </div>
        ))}
        <div className="mt-2 flex items-center gap-2.5 border-t border-border-subtle pt-2">
          <span className="w-44 shrink-0 text-[11.5px] font-semibold text-text-primary">
            Confluence
          </span>
          <span className="flex-1" />
          <span className="w-14 text-right font-mono text-sm font-semibold tabular-nums text-fin-blue">
            = {wf.total.toFixed(3)}
          </span>
        </div>
      </div>
      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {[
          `days_to_catalyst: ${components.days_to_catalyst ?? 'n/a'}`,
          `recency: ${components.recency.toFixed(2)} (${recencyLabel(components.days_to_catalyst)})`,
          `breadth: ${components.breadth.toFixed(2)}`,
          components.timeframe ? `timeframe: ${components.timeframe}` : null,
        ]
          .filter((s): s is string => s != null)
          .map((chip) => (
            <span
              key={chip}
              className="rounded-full border border-border-subtle px-2 py-0.5 font-mono text-[10.5px] text-text-secondary"
            >
              {chip}
            </span>
          ))}
      </div>
    </div>
  );
}

function TierTwo({ consensus }: { consensus: IntelligenceWhyItem['consensus'] }) {
  if (!consensus) {
    return (
      <div className="mt-4">
        <h4 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
          Tier 2 — the consensus behind it
        </h4>
        <p className="text-xs text-text-muted">No matching consensus row for this currency.</p>
      </div>
    );
  }
  const score = consensus.score;
  const figs: { label: string; value: string; cls?: string }[] = [
    { label: 'Score [-2,+2]', value: (score >= 0 ? '+' : '') + score.toFixed(2), cls: scoreColorClass(score) },
    { label: 'Confidence', value: `${pct(consensus.confidence <= 1 ? consensus.confidence * 100 : consensus.confidence)}%` },
    { label: 'Agreement', value: `${pct(consensus.agreement <= 1 ? consensus.agreement * 100 : consensus.agreement)}%` },
    { label: 'Tilt', value: scoreLabel(score) },
    { label: 'Brokers / Views', value: `${consensus.n_brokers} / ${consensus.n_views}` },
  ];

  return (
    <div className="mt-4">
      <h4 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        Tier 2 — the consensus behind it
      </h4>
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2">
        {figs.map((f) => (
          <div key={f.label}>
            <div className="text-[9.5px] uppercase tracking-wider text-text-muted">{f.label}</div>
            <div className={`font-mono text-base font-semibold tabular-nums ${f.cls ?? 'text-text-primary'}`}>
              {f.value}
            </div>
          </div>
        ))}
      </div>

      <div className="flex max-w-[360px] items-center gap-3">
        <div className="flex-1">
          <ConsensusScoreBar value={score} />
        </div>
        <span className={`w-12 text-right font-mono text-sm font-semibold tabular-nums ${scoreColorClass(score)}`}>
          {(score >= 0 ? '+' : '') + score.toFixed(2)}
        </span>
      </div>

      <div className="mt-3.5 flex h-3.5 overflow-hidden rounded">
        {SPLIT_SEGMENTS.map((s) => {
          const v = pct(consensus[s.key]);
          return (
            <div
              key={s.key}
              className="h-full"
              style={{ width: `${v}%`, backgroundColor: s.color }}
              title={`${s.label} ${v}%`}
            />
          );
        })}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-3 text-[10.5px] text-text-muted">
        {SPLIT_SEGMENTS.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: s.color }} />
            {s.label} {pct(consensus[s.key])}%
          </span>
        ))}
      </div>
    </div>
  );
}

function DeskRow({ desk }: { desk: IntelligenceWhyDesk }) {
  return (
    <div className="mb-2 rounded-md border border-border-subtle bg-bg-secondary p-2.5">
      <div className="mb-1.5 flex flex-wrap items-center gap-2.5">
        <span className="text-[12.5px] font-semibold text-text-primary">{desk.broker}</span>
        <span
          className={`rounded border px-1.5 py-px text-[9.5px] font-semibold uppercase tracking-wide ${classificationClass(desk.classification)}`}
        >
          {desk.classification}
        </span>
        <span className="font-mono text-[11px] text-text-muted">
          relevance {desk.relevance.toFixed(2)}
          {desk.conviction ? ` · ${desk.conviction} conviction` : ''}
          {desk.direction ? ` · ${desk.direction}` : ''}
        </span>
      </div>
      {desk.reason ? <p className="text-xs leading-snug text-text-secondary">{desk.reason}</p> : null}
    </div>
  );
}

function TierThree({ desks }: { desks: IntelligenceWhyDesk[] }) {
  return (
    <div className="mt-4">
      <h4 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        Tier 3 — supporting desks
      </h4>
      {desks.length > 0 ? (
        desks.map((d, i) => <DeskRow key={`${d.broker}-${i}`} desk={d} />)
      ) : (
        <p className="text-xs text-text-muted">No supporting desks recorded for this currency.</p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Panel
 * ------------------------------------------------------------------ */

export interface IntelligenceWhyPanelProps {
  item: IntelligenceWhyItem;
  /** Start expanded — used for deterministic SSR rendering under tests. */
  initialExpanded?: boolean;
}

/**
 * The expandable 3-tier "why this currency" drill-down for one confluence idea:
 *   Tier 1 — the `0.50·consensus + 0.30·event·recency + 0.20·breadth` score waterfall;
 *   Tier 2 — the consensus decomposition (divergent bar + figures + position split);
 *   Tier 3 — the supporting desks (classification badge + relevance + verbatim reason).
 *
 * The lead one-liner is explicitly LABELLED "synthesized — would require
 * generation": we do NOT generate it (no stored aggregated prose exists). Per
 * the global caveat, `w_time`/`w_event` are never surfaced.
 */
export default function IntelligenceWhyPanel({ item, initialExpanded }: IntelligenceWhyPanelProps) {
  const [open, setOpen] = useState(Boolean(initialExpanded));
  const bodyId = useId();

  return (
    <div className="mt-2 border-t border-border-subtle/60 pt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={bodyId}
        className="flex w-full items-center gap-2 text-left text-[11px] font-medium uppercase tracking-wider text-text-muted transition-colors hover:text-text-secondary"
      >
        <ChevronDown
          size={14}
          aria-hidden
          className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
        />
        Why {item.currency}
      </button>

      {open ? (
        <div id={bodyId} className="mt-2">
          <div className="rounded-md border border-dashed border-border-subtle bg-bg-secondary px-3 py-2.5">
            <span className="mb-1 block text-[9.5px] font-medium uppercase tracking-wider text-fin-amber">
              synthesized — would require generation
            </span>
            <p className="text-[12.5px] italic text-text-secondary">
              {item.currency} screens{' '}
              {item.direction ? item.direction.toLowerCase() : 'neutral'} at confluence{' '}
              {Number.isFinite(item.score) ? item.score.toFixed(2) : '—'}, driven mainly by{' '}
              {item.components.consensus_strength >= item.components.breadth
                ? 'broker consensus'
                : 'breadth of coverage'}{' '}
              with a catalyst {recencyLabel(item.components.days_to_catalyst)} out.
            </p>
          </div>

          <TierOne components={item.components} />
          <TierTwo consensus={item.consensus} />
          <TierThree desks={item.desks} />
        </div>
      ) : null}
    </div>
  );
}
