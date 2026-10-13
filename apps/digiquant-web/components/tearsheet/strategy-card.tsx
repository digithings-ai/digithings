/** Library index card for one published strategy (links to its tearsheet).
 *  The card dress + KPI grid are the finance-tearsheet family (#1463); the
 *  head composition and every figure below are this app's data wiring. */
import {
  TearsheetCard,
  TearsheetCardKpi,
  TearsheetCardKpis,
  fmtNum,
  fmtPct,
  toneClass,
} from "@digithings/ui";
import { AssetLogoFor } from "./asset-logo";
import { isDcaIndexEntry, lastAllocatedPctFromIndex, ALLOCATED_KPI_LABEL, VS_LUMP_KPI_LABEL, TOTAL_RETURN_KPI_LABEL } from "./dca";
import { LiveMetricsBadge } from "./live-metrics";
import { SignalDelayChip } from "./signal-delay";
import { strategyDisplayName, symbolBase } from "./strategy-names";
import { StrategyTypeChip } from "./strategy-type-chip";
import { cagrPctFromGrowth } from "./stats";
import { type StrategyIndexEntry } from "./types";

export function StrategyCard({ e }: { e: StrategyIndexEntry }) {
  const asset = symbolBase(e.symbol);
  const cagr = cagrPctFromGrowth(e.net_profit_pct, e.period_start, e.period_end);
  const avgTrade = e.avg_trade_pct ?? 0;
  const dca = isDcaIndexEntry(e);

  return (
    <TearsheetCard
      href={`/strategies/${e.strategy}`}
      className="gap-0 rounded-none p-0 [&_.ts-card-head]:px-3 [&_.ts-card-head]:py-2 [&_.ts-card-title]:gap-2"
    >
      <div className="ts-card-head">
        <div className="ts-card-title">
          <AssetLogoFor strategy={e.strategy} symbol={e.symbol} size={24} className="ts-card-logo" />
          <div className="ts-card-title-text">
            <span className="ts-card-name">{strategyDisplayName(e.strategy, e.label) || asset}</span>
            <StrategyTypeChip strategy={e.strategy} kind={e.kind} className="ts-card-kind" />
            <span className="ts-card-period">{e.period_start} → {e.period_end}</span>
            {e.signal_delay_days ? (
              <div className="mt-1">
                <SignalDelayChip days={e.signal_delay_days} />
              </div>
            ) : null}
          </div>
        </div>
        <LiveMetricsBadge generatedAt={e.generated_at} className="ts-card-live" />
      </div>
      <TearsheetCardKpis className="gap-x-3 gap-y-1 border-t border-hair px-3 py-2">
        <TearsheetCardKpi label={dca ? TOTAL_RETURN_KPI_LABEL : "CAGR"} value={<span className={toneClass(dca ? e.net_profit_pct : cagr)}>{fmtPct(dca ? e.net_profit_pct : cagr)}</span>} />
        <TearsheetCardKpi label="Max DD" value={<span className="is-neg">{fmtPct(e.max_drawdown_pct)}</span>} />
        {dca ? (
          <>
            <TearsheetCardKpi
              label={VS_LUMP_KPI_LABEL}
              value={<span className={toneClass(e.vs_lump_pct)}>{fmtPct(e.vs_lump_pct)}</span>}
            />
            <TearsheetCardKpi label={ALLOCATED_KPI_LABEL} value={fmtPct(lastAllocatedPctFromIndex(e))} />
          </>
        ) : (
          <>
            <TearsheetCardKpi label="Profit factor" value={fmtNum(e.profit_factor, 2)} />
            <TearsheetCardKpi label="Win rate" value={fmtPct(e.win_rate_pct)} />
            <TearsheetCardKpi label="Avg trade" value={<span className={toneClass(avgTrade)}>{fmtPct(avgTrade)}</span>} />
            <TearsheetCardKpi label="Trades" value={fmtNum(e.total_trades)} />
          </>
        )}
      </TearsheetCardKpis>
    </TearsheetCard>
  );
}
