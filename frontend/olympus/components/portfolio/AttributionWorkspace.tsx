'use client';

import { useMemo, useState } from 'react';
import { SegmentedControl, TabStrip, tabId, tabPanelId } from '@digithings/web';
import AttributionTab from '@/components/observability/AttributionTab';
import type { TableRow } from '@/lib/database.types';
import {
  computeDecisionScorecard,
  scoredDecisionEpisodes,
  type DecisionRecord,
} from '@/lib/decision-scorecard';
import DecisionAudit from './DecisionAudit';
import DecisionEffectiveness from './DecisionEffectiveness';

type WorkspaceView = 'effectiveness' | 'attribution' | 'audit';
export type AnalysisPeriod = '1w' | '1m' | '3m' | 'ytd' | '1y' | 'all';

const VIEWS: Array<{ id: WorkspaceView; label: string }> = [
  { id: 'effectiveness', label: 'Decision effectiveness' },
  { id: 'attribution', label: 'Book attribution' },
  { id: 'audit', label: 'Audit' },
];

const PERIODS: Array<{ value: AnalysisPeriod; label: string }> = [
  { value: '1w', label: '1W' },
  { value: '1m', label: '1M' },
  { value: '3m', label: '3M' },
  { value: 'ytd', label: 'YTD' },
  { value: '1y', label: '1Y' },
  { value: 'all', label: 'All history' },
];

function latestDate(decisions: TableRow<'decision_log'>[]): string | null {
  return decisions.reduce<string | null>(
    (latest, decision) =>
      decision.run_date && (!latest || decision.run_date > latest) ? decision.run_date : latest,
    null
  );
}

function periodStart(period: AnalysisPeriod, asOf: string | null): string | null {
  if (period === 'all' || !asOf) return null;
  if (period === 'ytd') return `${asOf.slice(0, 4)}-01-01`;
  const start = new Date(`${asOf}T00:00:00Z`);
  if (period === '1w') {
    start.setUTCDate(start.getUTCDate() - 7);
    return start.toISOString().slice(0, 10);
  }
  const day = start.getUTCDate();
  start.setUTCDate(1);
  if (period === '1m') start.setUTCMonth(start.getUTCMonth() - 1);
  if (period === '3m') start.setUTCMonth(start.getUTCMonth() - 3);
  if (period === '1y') start.setUTCFullYear(start.getUTCFullYear() - 1);
  const lastDay = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0))
    .getUTCDate();
  start.setUTCDate(Math.min(day, lastDay));
  return start.toISOString().slice(0, 10);
}

export function filterDecisionsByPeriod(
  decisions: TableRow<'decision_log'>[],
  period: AnalysisPeriod
): TableRow<'decision_log'>[] {
  const start = periodStart(period, latestDate(decisions));
  return start ? decisions.filter((decision) => decision.run_date >= start) : decisions;
}

export function decisionsForAnalysisPeriod(
  decisions: TableRow<'decision_log'>[],
  period: AnalysisPeriod
): DecisionRecord[] {
  const start = periodStart(period, latestDate(decisions));
  const scored = scoredDecisionEpisodes(decisions)
    .filter((item) => !start || (item.decision.run_date ?? '') >= start)
    .map((item) => item.decision);
  const pending = filterDecisionsByPeriod(decisions, period).filter(
    (decision) => decision.status === 'pending'
  );
  return [...scored, ...pending];
}

function verdict(meanAlphaPct: number): { label: string; tone: string } {
  if (meanAlphaPct > 0) return { label: 'Positive decision edge', tone: 'text-up' };
  if (meanAlphaPct < 0) return { label: 'Negative decision edge', tone: 'text-down' };
  return { label: 'No measured decision edge', tone: 'text-ink-soft' };
}

export default function AttributionWorkspace({
  attribution,
  attributionDate,
  decisions,
}: {
  attribution: TableRow<'position_attribution'>[];
  attributionDate: string | null;
  decisions: TableRow<'decision_log'>[];
}) {
  const [view, setView] = useState<WorkspaceView>('effectiveness');
  const [period, setPeriod] = useState<AnalysisPeriod>('all');
  const scopedDecisions = useMemo(
    () => filterDecisionsByPeriod(decisions, period),
    [decisions, period]
  );
  const analysisDecisions = useMemo(
    () => decisionsForAnalysisPeriod(decisions, period),
    [decisions, period]
  );
  const scorecard = useMemo(
    () => computeDecisionScorecard(analysisDecisions),
    [analysisDecisions]
  );
  const scoredDecisions = useMemo(
    () => scoredDecisionEpisodes(analysisDecisions),
    [analysisDecisions]
  );
  const state = scorecard ? verdict(scorecard.meanAlphaPct) : null;
  const decisionAsOf = latestDate(decisions);
  const asOf = view === 'attribution' ? attributionDate : decisionAsOf ?? attributionDate;
  const rangeStart = scopedDecisions.reduce<string | null>(
    (earliest, decision) =>
      decision.run_date && (!earliest || decision.run_date < earliest) ? decision.run_date : earliest,
    null
  );
  const sampleSize = scoredDecisions.length >= 50
    ? 'larger sample'
    : scoredDecisions.length >= 20
      ? 'moderate sample'
      : 'limited sample';
  const activeIndex = VIEWS.findIndex((item) => item.id === view);
  const activeView = VIEWS[activeIndex];

  return (
    <div className="space-y-6">
      <header className="border-y border-hair bg-surface">
        <div className="grid gap-5 px-4 py-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-end md:px-5">
          <div className="space-y-2">
            <p className="font-mono text-[11px] uppercase text-ink-mute">Decision monitor</p>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <strong className={`font-display text-2xl md:text-3xl ${state?.tone ?? 'text-ink'}`}>
                {state?.label ?? 'Awaiting resolved outcomes'}
              </strong>
              <span className="text-xs text-ink-mute">
                {scorecard
                  ? `${scorecard.nResolved} scored decisions · ${sampleSize}`
                  : 'No scored sample'}
              </span>
            </div>
            <p className="font-mono text-[11px] text-ink-mute">
              {period === 'all' ? 'From inception' : PERIODS.find((item) => item.value === period)?.label}
              {rangeStart && decisionAsOf ? ` · ${rangeStart} to ${decisionAsOf}` : ''}
            </p>
          </div>
          <div className="font-mono text-[11px] uppercase text-ink-mute md:text-right">
            <span className="block">As of</span>
            <strong className="text-ink">{asOf ?? '—'}</strong>
          </div>
        </div>

        {view !== 'attribution' ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hair px-4 py-3 md:px-5">
            <span className="font-mono text-[11px] uppercase text-ink-mute">Analysis period</span>
            <SegmentedControl
              options={PERIODS}
              value={period}
              onChange={setPeriod}
              dress="accent"
              aria-label="Analysis period"
            />
          </div>
        ) : (
          <div className="border-t border-hair px-4 py-3 text-right font-mono text-[11px] text-ink-mute md:px-5">
            Latest stored book window
          </div>
        )}

        <div className="overflow-x-auto border-t border-hair px-3 py-2">
          <TabStrip
            tabs={VIEWS}
            active={activeIndex}
            onChange={(index) => setView(VIEWS[index].id)}
            label="Attribution workspace"
            variant="underline"
            sharedPanel
          />
        </div>
      </header>

      <div
        role="tabpanel"
        id={tabPanelId('Attribution workspace', activeView.id)}
        aria-labelledby={tabId('Attribution workspace', activeView.id)}
      >
        {view === 'effectiveness' ? (
          <DecisionEffectiveness decisions={analysisDecisions} />
        ) : null}
        {view === 'attribution' ? (
          <AttributionTab attribution={attribution} date={attributionDate} embedded />
        ) : null}
        {view === 'audit' ? <DecisionAudit decisions={scopedDecisions} /> : null}
      </div>
    </div>
  );
}