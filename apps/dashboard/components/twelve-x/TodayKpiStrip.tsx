'use client';

import { RangeTrack, Stat } from '@digithings/ui/ui';
import { formatCountdown, type TodayKpis } from '@/lib/twelve-x/kpis';

const pct = (x: number) => `${Math.round(x * 100)}%`;

/**
 * Five-second state of the desk: run date, idea count (with disputes), brief and
 * broker counts, the 30-day resolved-idea hit rate as a Wilson interval on a
 * 0-100% track, and the next high-impact release. Every tile degrades to an em
 * dash rather than disappearing so the strip keeps its shape.
 */
export default function TodayKpiStrip({ kpis }: { kpis: TodayKpis }) {
  const { hit, nextHighImpact: next } = kpis;
  return (
    <section
      aria-label="Today at a glance"
      data-testid="twelvex-kpi-strip"
      className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6"
    >
      <Stat label="Run" value={kpis.runDate} />
      <Stat
        label="Ideas"
        value={kpis.ideaCount}
        delta={kpis.disputedCount > 0 ? `${kpis.disputedCount} disputed` : undefined}
        deltaTone="warn"
      />
      <Stat label="Briefs" value={kpis.briefCount} />
      <Stat label="Brokers" value={kpis.brokerCount} />
      <Stat
        label="30d hit rate"
        value={hit ? pct(hit.rate) : null}
        hint={hit ? `n=${hit.n}, ${pct(hit.low)}–${pct(hit.high)}` : 'no resolved ideas'}
        spark={
          hit ? (
            <RangeTrack
              className="w-20"
              low={0}
              high={1}
              label="Hit-rate 95% interval"
              markers={[
                { kind: 'level', value: hit.low, label: 'Interval low' },
                { kind: 'level', value: hit.high, label: 'Interval high' },
                { kind: 'current', value: hit.rate, label: 'Hit rate' },
              ]}
              format={pct}
            />
          ) : undefined
        }
      />
      <Stat
        label="Next high impact"
        value={next ? formatCountdown(next.minutesAway) : null}
        hint={next ? `${next.country} ${next.name}` : 'none scheduled in feed'}
      />
    </section>
  );
}
