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
} from "@digithings/web";
import { AssetLogoFor } from "./asset-logo";
import { LiveMetricsBadge } from "./live-metrics";
import { SignalDelayChip } from "./signal-delay";
import { symbolBase } from "./strategy-names";
import { cagrPctFromGrowth } from "./stats";
import { type StrategyIndexEntry } from "./types";

export function StrategyCard({ e }: { e: StrategyIndexEntry }) {
  const asset = symbolBase(e.symbol);
  const cagr = cagrPctFromGrowth(e.net_profit_pct, e.period_start, e.period_end);
  const avgTrade = e.avg_trade_pct ?? 0;

  return (
    <TearsheetCard href={`/strategies/${e.strategy}`}>
      <div className="ts-card-head">
        <div className="ts-card-title">
          <AssetLogoFor strategy={e.strategy} symbol={e.symbol} size={32} className="ts-card-logo" />
          <div className="ts-card-title-text">
            <span className="ts-card-name">{asset}</span>
            <span className="ts-card-period">{e.period_start} → {e.period_end}</span>
            {e.signal_delay_days ? (
              <div className="mt-1.5">
                <SignalDelayChip days={e.signal_delay_days} />
              </div>
            ) : null}
          </div>
        </div>
        <LiveMetricsBadge generatedAt={e.generated_at} className="ts-card-live" />
      </div>
      <TearsheetCardKpis>
        <TearsheetCardKpi label="CAGR" value={<span className={toneClass(cagr)}>{fmtPct(cagr)}</span>} />
        <TearsheetCardKpi label="Max DD" value={<span className="is-neg">{fmtPct(e.max_drawdown_pct)}</span>} />
        <TearsheetCardKpi label="Profit factor" value={fmtNum(e.profit_factor, 2)} />
        <TearsheetCardKpi label="Win rate" value={fmtPct(e.win_rate_pct)} />
        <TearsheetCardKpi label="Avg trade" value={<span className={toneClass(avgTrade)}>{fmtPct(avgTrade)}</span>} />
        <TearsheetCardKpi label="Trades" value={fmtNum(e.total_trades)} />
      </TearsheetCardKpis>
    </TearsheetCard>
  );
}
