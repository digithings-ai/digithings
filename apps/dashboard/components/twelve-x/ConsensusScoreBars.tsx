'use client';

import { barFillPct, tickPct } from '@/lib/twelve-x/consensus-bar';

/** Kind of reference marker laid over the divergent score track. */
export type MarkerKind = 'actual' | 'prior' | 'ago' | 'baseline';

/** A single legend-coded reference tick. */
export interface ConsensusMarker {
  /**
   * Score in `[-SCORE_MAX, SCORE_MAX]`; positioned via `tickPct`. May be
   * `null`/`undefined` for markers the caller cannot derive yet (e.g. the
   * yesterday/5d-ago average on a short or partial-start series) — such markers
   * are dropped rather than rendered as a spurious dead-center tick, matching
   * the demo's `divergentBarMulti` `.filter(v != null)` recipe.
   */
  value: number | null | undefined;
  /** Visual class bucket: bright (actual) / accent (prior, baseline) / muted (ago). */
  kind: MarkerKind;
  /** Hover title text. */
  label: string;
}

export interface ConsensusScoreBarProps {
  /** Bar fill magnitude/direction; `>= 0` ⇒ bull (right of center), `< 0` ⇒ bear. */
  value: number;
  /** Optional reference ticks. Omit (or pass `[]`) for the plain single-value bar. */
  markers?: ConsensusMarker[];
}

/** marker kind → `.dbar-tick` modifier class (matches the demo's `.dbar-*` recipe). */
const TICK_CLASS: Record<MarkerKind, string> = {
  actual: 't-actual', // bright (var(--ink))
  prior: 't-yday', // accent
  baseline: 't-yday', // accent
  ago: 't-ago', // muted
};

/**
 * Divergent consensus score bar: a zero-centered track with a green (bull,
 * `value >= 0`) or red (bear) fill growing out from the center, plus an
 * optional set of legend-coded reference ticks.
 *
 * Implements the frozen visual spec's `divergentBarMulti` / `.dbar-*` recipe.
 * With no markers it degrades to the plain single-value bar reused by the
 * Consensus table and Intelligence surfaces.
 */
export function ConsensusScoreBar({ value, markers }: ConsensusScoreBarProps) {
  const bull = value >= 0;
  const fillWidth = `${barFillPct(value)}%`;

  return (
    <div className="dbar-wrap">
      <div className="dbar-track">
        <span className="dbar-zero" />
        <span
          className={`dbar-fill ${bull ? 'bull' : 'bear'}`}
          style={{ width: fillWidth }}
        />
      </div>
      {(markers ?? [])
        .filter((m) => Number.isFinite(m.value))
        .map((m, i) => (
          <span
            key={`${m.kind}-${i}`}
            className={`dbar-tick ${TICK_CLASS[m.kind]}`}
            style={{ left: `calc(${tickPct(m.value as number)}% - 1px)` }}
            title={m.label}
          />
        ))}
    </div>
  );
}

export default ConsensusScoreBar;
