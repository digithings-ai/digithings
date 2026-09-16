'use client';

import type {
  ConsensusAccuracySummary,
  ConsensusStabilitySummary,
  IdeaOutcomeSummary,
} from '@/lib/twelve-x/track-record';
import { Card } from '@digithings/web/ui';
import { TwelveXSectionHeading } from './TwelveXSectionHeading';
import WilsonStat from './WilsonStat';

function Count({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="min-w-[4rem]">
      <p className="text-[10px] font-medium uppercase tracking-wider text-ink-mute">{label}</p>
      <p className="font-mono text-sm tabular-nums text-ink">{value}</p>
    </div>
  );
}

/**
 * Calibration readout for the Track record tab: idea hit-rates (all / long /
 * short) plus consensus stability and 5-day accuracy, every rate as a Wilson
 * 95% interval via {@link WilsonStat}. Pure render over the
 * `summarize*` outputs in `lib/twelve-x/track-record`.
 */
export function CalibrationPanel({
  ideaSummary,
  consensusStability,
  consensusAccuracy,
}: {
  ideaSummary: IdeaOutcomeSummary;
  consensusStability: ConsensusStabilitySummary[];
  consensusAccuracy: ConsensusAccuracySummary;
}) {
  return (
    <Card data-reveal className="gap-0 space-y-4 p-5" data-testid="calibration-panel">
      <TwelveXSectionHeading>Calibration</TwelveXSectionHeading>
      <p className="max-w-2xl text-xs text-ink-mute">
        Hit-rates with 95% Wilson intervals. Small samples widen the interval instead of
        hiding — treat narrow-looking point estimates with few observations with caution.
      </p>

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          Idea outcomes
        </h3>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <WilsonStat label="All ideas" interval={ideaSummary.interval} />
          <WilsonStat label="Long" interval={ideaSummary.longInterval} />
          <WilsonStat label="Short" interval={ideaSummary.shortInterval} />
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <Count label="Resolved" value={ideaSummary.resolvedCount} />
          <Count label="Wins" value={ideaSummary.winCount} />
          <Count label="Losses" value={ideaSummary.lossCount} />
          <Count label="Carried (raw)" value={ideaSummary.carriedCount} />
          <Count label="Missing rates" value={ideaSummary.missingCount} />
          <Count label="Significant" value={ideaSummary.significantCount} />
        </div>
      </div>

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          Consensus stability
        </h3>
        {consensusStability.length === 0 ? (
          <p className="text-xs text-ink-mute">No consensus jump data yet.</p>
        ) : (
          <div className="space-y-3">
            {consensusStability.map((s) => (
              <div key={s.weighted ? 'weighted' : 'unweighted'} className="space-y-2">
                <p className="font-mono text-[11px] text-ink-soft">
                  {s.weighted ? 'Weighted' : 'Unweighted'} · {s.nJumps} jumps
                  {s.medianAbsDelta !== null ? ` · median |Δ| ${s.medianAbsDelta.toFixed(2)}` : ''}
                </p>
                <div className="flex flex-wrap gap-x-6 gap-y-2">
                  <WilsonStat label="Sign flips" interval={s.signFlipPct} />
                  <WilsonStat label="Large jumps" interval={s.largeJumpPct} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          Consensus 5-day accuracy
        </h3>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <WilsonStat label="Direction hit" interval={consensusAccuracy.interval} />
          <WilsonStat label="Significant hit" interval={consensusAccuracy.significantInterval} />
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <Count label="Carried" value={consensusAccuracy.carriedCount} />
          <Count label="Missing rates" value={consensusAccuracy.missingCount} />
        </div>
      </div>
    </Card>
  );
}

export default CalibrationPanel;
