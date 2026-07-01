/** Library index card for one published strategy (links to its tearsheet). */
import { AssetLogoFor } from "./asset-logo";
import { fmtNum, fmtPct, toneClass } from "./format";
import { LiveMetricsBadge } from "./live-metrics";
import { symbolBase } from "./strategy-names";
import { cagrPctFromGrowth } from "./stats";
import { type StrategyIndexEntry } from "./types";

function CardKpi({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="ts-card-kpi">
      <span className="ts-card-kpi-label">{label}</span>
      <span className="ts-card-kpi-value">{value}</span>
    </div>
  );
}

export function StrategyCard({ e }: { e: StrategyIndexEntry }) {
  const asset = symbolBase(e.symbol);
  const cagr = cagrPctFromGrowth(e.net_profit_pct, e.period_start, e.period_end);
  const avgTrade = e.avg_trade_pct ?? 0;

  return (
    <a className="ts-card" href={`/strategies/${e.strategy}`}>
      <div className="ts-card-head">
        <div className="ts-card-title">
          <AssetLogoFor strategy={e.strategy} symbol={e.symbol} size={32} className="ts-card-logo" />
          <div className="ts-card-title-text">
            <span className="ts-card-name">{asset}</span>
            <span className="ts-card-period">{e.period_start} → {e.period_end}</span>
          </div>
        </div>
        <LiveMetricsBadge generatedAt={e.generated_at} className="ts-card-live" />
      </div>
      <div className="ts-card-kpis">
        <CardKpi label="CAGR" value={<span className={toneClass(cagr)}>{fmtPct(cagr)}</span>} />
        <CardKpi label="Max DD" value={<span className="is-neg">{fmtPct(e.max_drawdown_pct)}</span>} />
        <CardKpi label="Profit factor" value={fmtNum(e.profit_factor, 2)} />
        <CardKpi label="Win rate" value={fmtPct(e.win_rate_pct)} />
        <CardKpi label="Avg trade" value={<span className={toneClass(avgTrade)}>{fmtPct(avgTrade)}</span>} />
        <CardKpi label="Trades" value={fmtNum(e.total_trades)} />
      </div>
    </a>
  );
}
