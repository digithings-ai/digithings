/**
 * Pure derivation of the Today KPI strip: run state, idea/brief/broker counts,
 * the trailing-30-day resolved-idea hit rate (Wilson interval) and the next
 * high-impact macro release. No fetching, no clock reads (`now` is injected).
 */
import type { FxBriefRow, FxEconomicCalendarRow, FxIdeaEvalRow, FxTradeIdeaRow } from './types';
import { summarizeIdeaOutcomes } from './track-record';
import type { WilsonInterval } from './wilson';

export const HIT_RATE_WINDOW_DAYS = 30;

export interface NextHighImpact {
  name: string;
  country: string;
  at: string;
  minutesAway: number;
}

export interface TodayKpis {
  runDate: string | null;
  ideaCount: number;
  disputedCount: number;
  briefCount: number;
  brokerCount: number | null;
  /** Resolved-idea hit rate over the window; `null` when nothing resolved. */
  hit: WilsonInterval | null;
  nextHighImpact: NextHighImpact | null;
}

type KpiEvent = Pick<
  FxEconomicCalendarRow,
  'impact' | 'event_name' | 'country' | 'event_datetime_utc'
>;

export interface TodayKpiInput {
  runDate: string | null;
  ideas: Pick<FxTradeIdeaRow, 'rank'>[];
  disputedCount: number;
  briefs: Pick<FxBriefRow, 'broker_name'>[];
  digest: { broker_count: number } | null;
  events: KpiEvent[];
  ideaEval: FxIdeaEvalRow[];
  now: Date;
}

function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Eval rows whose board date falls in the trailing window ending at `now`. */
export function evalInWindow(
  rows: FxIdeaEvalRow[],
  now: Date,
  days = HIT_RATE_WINDOW_DAYS,
): FxIdeaEvalRow[] {
  const from = isoDay(new Date(now.getTime() - days * 86_400_000));
  const to = isoDay(now);
  return rows.filter((r) => r.run_date >= from && r.run_date <= to);
}

export function nextHighImpactEvent(events: KpiEvent[], now: Date): NextHighImpact | null {
  let best: { at: Date; row: KpiEvent } | null = null;
  for (const e of events) {
    if (e.impact?.toLowerCase() !== 'high' || !e.event_datetime_utc) continue;
    const at = new Date(e.event_datetime_utc);
    if (Number.isNaN(at.getTime()) || at.getTime() < now.getTime()) continue;
    if (!best || at.getTime() < best.at.getTime()) best = { at, row: e };
  }
  if (!best) return null;
  return {
    name: best.row.event_name,
    country: best.row.country,
    at: best.at.toISOString(),
    minutesAway: Math.round((best.at.getTime() - now.getTime()) / 60_000),
  };
}

export function deriveTodayKpis(input: TodayKpiInput): TodayKpis {
  const summary = summarizeIdeaOutcomes(evalInWindow(input.ideaEval, input.now));
  const named = new Set(input.briefs.map((b) => b.broker_name).filter((n): n is string => !!n));
  return {
    runDate: input.runDate,
    ideaCount: input.ideas.length,
    disputedCount: input.disputedCount,
    briefCount: input.briefs.length,
    brokerCount: input.digest ? input.digest.broker_count : named.size > 0 ? named.size : null,
    hit: summary.resolvedCount > 0 ? summary.interval : null,
    nextHighImpact: nextHighImpactEvent(input.events, input.now),
  };
}

/** `in 35m`, `in 2h 10m`, `now` — compact countdown. */
export function formatCountdown(minutes: number): string {
  if (minutes <= 0) return 'now';
  if (minutes < 60) return `in ${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `in ${h}h` : `in ${h}h ${m}m`;
}
