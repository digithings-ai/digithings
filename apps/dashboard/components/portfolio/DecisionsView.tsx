'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { DivergingBars, SegmentedControl, Sparkline, Stat } from '@digithings/ui/ui';
import type { TableRow } from '@/lib/database.types';
import { computeDecisionScorecard, scoredDecisionEpisodes } from '@/lib/decision-scorecard';
import {
  ANALYSIS_PERIODS,
  buildDecisionEdgeTrend,
  convictionEdgeBars,
  decisionsForAnalysisPeriod,
  earliestDecisionDate,
  edgeVerdict,
  filterDecisionsByPeriod,
  latestDecisionDate,
  reviewQueue,
  sampleLabel,
  stanceEdges,
  type AnalysisPeriod,
} from '@/lib/portfolio-decisions-view';
import { signedPct } from '@/lib/portfolio-performance-view';
import type { DecisionsPaneId } from '@/lib/portfolio-url-state';
import DecisionAudit from './DecisionAudit';

const VERDICT_TEXT = { accent: 'text-accent', warn: 'text-warn', mute: 'text-ink-mute' } as const;

const pct1 = (v: number) => signedPct(v, 2);

/**
 * Decisions: does the PM's judgement add value? Edge pane is chart-first
 * (cumulative edge line, conviction calibration, stance and worst-call bars);
 * Theses is the market-thesis story spine (passed in); Audit is the record.
 * Edge is alpha vs the recorded benchmark, so bars use the signed tone while the
 * verdict itself stays in the health vocabulary (accent / warn / ink-mute).
 */
export default function DecisionsView({
  decisions,
  pane,
  onPaneChange,
  thesesPane,
}: {
  decisions: TableRow<'decision_log'>[];
  pane: DecisionsPaneId;
  onPaneChange: (pane: DecisionsPaneId) => void;
  /** When omitted the Theses segment is hidden (e.g. the /portfolio/attribution route). */
  thesesPane?: ReactNode;
}) {
  const [period, setPeriod] = useState<AnalysisPeriod>('all');
  const scoped = useMemo(() => filterDecisionsByPeriod(decisions, period), [decisions, period]);
  const analysis = useMemo(() => decisionsForAnalysisPeriod(decisions, period), [decisions, period]);
  const scorecard = useMemo(() => computeDecisionScorecard(analysis), [analysis]);
  const episodes = useMemo(() => scoredDecisionEpisodes(analysis), [analysis]);
  const trend = useMemo(() => buildDecisionEdgeTrend(episodes), [episodes]);
  const stances = useMemo(() => stanceEdges(episodes), [episodes]);
  const worst = useMemo(() => reviewQueue(episodes), [episodes]);

  const verdict = edgeVerdict(scorecard ? scorecard.meanAlphaPct : null);
  const asOf = latestDecisionDate(decisions);
  const from = earliestDecisionDate(scoped);
  const paneOptions = [
    { value: 'edge', label: 'Edge' },
    ...(thesesPane ? [{ value: 'theses', label: 'Theses' }] : []),
    { value: 'audit', label: 'Audit' },
  ] as Array<{ value: DecisionsPaneId; label: string }>;
  const activePane = pane === 'theses' && !thesesPane ? 'edge' : pane;

  return (
    <div data-testid="decisions-view" className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <p className="font-mono text-[11px] uppercase tracking-wider text-ink-mute">Decision monitor</p>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <strong data-testid="decision-verdict" className={`font-display text-xl ${VERDICT_TEXT[verdict.tone]}`}>
              {verdict.label}
            </strong>
            <span className="text-xs text-ink-mute">
              {scorecard
                ? `${scorecard.nResolved} scored decisions · ${sampleLabel(scorecard.nResolved)}`
                : 'No scored sample'}
            </span>
          </div>
          <p className="font-mono text-[11px] text-ink-mute">
            {period === 'all' ? 'From inception' : ANALYSIS_PERIODS.find((p) => p.value === period)?.label}
            {from && asOf ? ` · ${from} to ${asOf}` : ''}
            {' · as of '}
            <strong className="text-ink">{asOf ?? '—'}</strong>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SegmentedControl
            dress="accent"
            aria-label="Decisions section"
            options={paneOptions}
            value={activePane}
            onChange={onPaneChange}
          />
          {activePane !== 'theses' ? (
            <SegmentedControl
              dress="accent"
              aria-label="Analysis period"
              options={ANALYSIS_PERIODS}
              value={period}
              onChange={setPeriod}
            />
          ) : null}
        </div>
      </header>

      {activePane === 'edge' ? (
        scorecard ? (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
              <Stat label="Mean decision edge" value={signedPct(scorecard.meanAlphaPct)} hint="vs recorded benchmark" />
              <Stat
                label="Directional hit rate"
                value={`${scorecard.hitRatePct.toFixed(1)}%`}
                hint="correct directional calls"
              />
              <Stat
                label="Edge consistency"
                value={scorecard.informationRatio.toFixed(2)}
                hint="mean edge / variability"
              />
              <Stat
                label="Decisions scored"
                value={String(scorecard.nResolved)}
                hint={`${scorecard.nPending} awaiting outcomes`}
              />
            </div>

            <section aria-labelledby="decision-edge-heading" className="border border-hair p-3">
              <h2 id="decision-edge-heading" className="text-sm font-semibold text-ink">
                Decision edge over time
              </h2>
              <p className="mb-2 font-mono text-[11px] text-ink-mute">
                Cumulative mean decision edge · all scored decisions in period
              </p>
              {trend.length >= 2 ? (
                <Sparkline
                  data-testid="decision-edge-trend"
                  values={trend.map((p) => p.value)}
                  width={640}
                  height={120}
                  area
                  className="h-28 w-full"
                  label={`Cumulative mean decision edge across ${trend.length} dates, from ${pct1(trend[0].value)} on ${trend[0].date} to ${pct1(trend[trend.length - 1].value)} on ${trend[trend.length - 1].date}.`}
                />
              ) : (
                <p className="flex h-28 items-center justify-center border border-dashed border-hair text-xs text-ink-mute">
                  Two dated decisions are required to draw the trend.
                </p>
              )}
            </section>

            <div className="grid gap-5 lg:grid-cols-2">
              <section aria-labelledby="conviction-heading" className="border border-hair p-3">
                <div className="flex items-baseline justify-between gap-3">
                  <h2 id="conviction-heading" className="text-sm font-semibold text-ink">
                    Edge by conviction
                  </h2>
                  <span
                    data-testid="calibration-evidence"
                    className={`font-mono text-[11px] uppercase ${
                      scorecard.calibrationEvidence === 'aligned'
                        ? 'text-accent'
                        : scorecard.calibrationEvidence === 'inverted'
                          ? 'text-warn'
                          : 'text-ink-mute'
                    }`}
                  >
                    {scorecard.calibrationEvidence === 'insufficient'
                      ? 'Insufficient evidence'
                      : scorecard.calibrationEvidence}
                  </span>
                </div>
                <DivergingBars
                  className="mt-3"
                  label="Mean decision edge by conviction bucket"
                  items={convictionEdgeBars(scorecard).map((b) => ({
                    id: b.bucket,
                    label: `${b.bucket} (n=${b.n})`,
                    value: b.meanAlphaPct,
                    display: b.meanAlphaPct == null ? '—' : pct1(b.meanAlphaPct),
                  }))}
                  emptyLabel="No conviction buckets yet"
                />
                <p className="mt-3 text-xs text-ink-mute">
                  Verdict requires at least two conviction buckets with 10 or more independent decisions.
                </p>
              </section>

              <section aria-labelledby="stance-heading" className="border border-hair p-3">
                <h2 id="stance-heading" className="text-sm font-semibold text-ink">
                  Edge by stance
                </h2>
                <DivergingBars
                  className="mt-3"
                  label="Mean decision edge by stance"
                  items={stances.map((s) => ({
                    id: s.stance,
                    label: `${s.stance} (n=${s.n}, hit ${s.hitRatePct.toFixed(0)}%)`,
                    value: s.meanAlphaPct,
                    display: pct1(s.meanAlphaPct),
                  }))}
                />
              </section>
            </div>

            <section aria-labelledby="review-queue-heading" className="border border-hair p-3">
              <div className="flex items-baseline justify-between gap-3">
                <h2 id="review-queue-heading" className="text-sm font-semibold text-ink">
                  Review queue
                </h2>
                <span className="font-mono text-[11px] text-ink-mute">lowest decision edge</span>
              </div>
              <DivergingBars
                className="mt-3"
                label="Scored decisions with the lowest edge"
                items={worst.map((e, i) => ({
                  id: e.decision.id ?? `${e.decision.ticker}-${i}`,
                  label: `${e.decision.ticker ?? '—'} ${e.decision.stance ?? ''} · ${e.decision.run_date ?? '—'}`.trim(),
                  value: e.directionalAlpha * 100,
                  display: pct1(e.directionalAlpha * 100),
                }))}
              />
            </section>
          </div>
        ) : (
          <p className="border-y border-hair py-8 text-sm text-ink-mute">
            No resolved directional decisions are available yet.
          </p>
        )
      ) : null}

      {activePane === 'theses' ? thesesPane : null}
      {activePane === 'audit' ? <DecisionAudit decisions={scoped} /> : null}
    </div>
  );
}
