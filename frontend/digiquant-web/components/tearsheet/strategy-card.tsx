/** Library index card for one published strategy (links to its tearsheet). */
import { fmtCompact, fmtNum, fmtPct, toneClass } from "./format";
import { type StrategyIndexEntry } from "./types";

function CardKpi({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="ts-card-kpi">
      <span className="ts-card-kpi-label">{label}</span>
      <span className="ts-card-kpi-value">{value}</span>
    </div>
  );
}

function pct(v: number): string {
  if (Math.abs(v) >= 10000) return fmtCompact(v) + "%";
  return fmtPct(v);
}

export function StrategyCard({ e }: { e: StrategyIndexEntry }) {
  return (
    <a className="ts-card" href={`/strategies/${e.strategy}`}>
      <div className="ts-card-head">
        <span className="ts-card-name">{e.strategy}</span>
        <span className="ts-chip">{e.symbol}</span>
      </div>
      <div className="ts-card-period">{e.period_start} → {e.period_end}</div>
      <div className="ts-card-kpis">
        <CardKpi label="Net profit" value={<span className={toneClass(e.net_profit_pct)}>{pct(e.net_profit_pct)}</span>} />
        <CardKpi label="Max DD" value={<span className="is-neg">{pct(e.max_drawdown_pct)}</span>} />
        <CardKpi label="Profit factor" value={fmtNum(e.profit_factor, 2)} />
        <CardKpi label="Win rate" value={pct(e.win_rate_pct)} />
        <CardKpi label="Trades" value={fmtNum(e.total_trades)} />
      </div>
      <span className="ts-card-cta">View tearsheet →</span>
    </a>
  );
}
