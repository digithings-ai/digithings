import { CandlestickChart, TimeSeries } from "./charts";
import { Kpi, KpiStrip } from "./KpiStrip";
import { TradeLogTable } from "./TradeLogTable";
import type { StrategySheetMetric, StrategySheetModel } from "./strategy-sheet-model";

const DASH = "—";

function Figure({ metric }: { metric: StrategySheetMetric }) {
  const tone = metric.tone === "pos" ? "is-pos" : metric.tone === "neg" ? "is-neg" : undefined;
  return <span className={tone}>{metric.value ?? DASH}</span>;
}

/**
 * One strategy tear sheet. Unpublished figures are an em dash. A chart is
 * mounted only when the model already kept a series of two or more values.
 * No status sentence and no backtest chips.
 */
export function StrategyTearsheet({ model }: { model: StrategySheetModel }) {
  return (
    <div className="ts-print-root" data-strategy-tearsheet="">
      <header className="ts-header">
        <div className="ts-header-main">
          <h2 className="ts-h1">{model.title}</h2>
          {model.symbol ? <p className="ts-meta-text m-0">{model.symbol}</p> : null}
        </div>
      </header>

      <section className="ts-position" aria-label="Current position">
        <div className="ts-position-head">
          <span className="ts-panel-label">Current position</span>
        </div>
        <dl className="m-0 grid grid-cols-2 gap-px border border-hair bg-hair sm:grid-cols-4">
          {model.position.map((item) => (
            <div key={item.label} className="bg-surface px-3 py-2">
              <dt className="font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">{item.label}</dt>
              <dd className="m-0 mt-1 font-mono text-[0.9rem] leading-none text-ink">
                <Figure metric={item} />
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <KpiStrip primary ariaLabel="Headline performance">
        {model.metrics.map((item) => (
          <Kpi key={item.label} label={item.label} value={<Figure metric={item} />} />
        ))}
      </KpiStrip>

      {model.price ? (
        <section className="ts-panel" aria-label="Price">
          <h3 className="ts-panel-label">Price</h3>
          <div className="ts-chart">
            <CandlestickChart
              bars={model.price}
              trades={[]}
              height={320}
              ariaLabel={`${model.symbol || model.title} price`}
            />
          </div>
        </section>
      ) : null}

      {model.equity ? (
        <section className="ts-panel" aria-label="Performance">
          <h3 className="ts-panel-label">Performance</h3>
          <div className="ts-chart">
            <TimeSeries points={model.equity} height={280} ariaLabel={`${model.title} equity`} />
          </div>
        </section>
      ) : null}

      {model.drawdown ? (
        <section className="ts-panel" aria-label="Drawdown">
          <h3 className="ts-panel-label">Drawdown</h3>
          <div className="ts-chart">
            <TimeSeries
              points={model.drawdown}
              height={220}
              tone="down"
              ariaLabel={`${model.title} drawdown`}
            />
          </div>
        </section>
      ) : null}

      <section className="ts-panel" aria-label="Entries and exits">
        <h3 className="ts-panel-label">Entries and exits</h3>
        <TradeLogTable
          ariaLabel="Entries and exits"
          columns={(model.trades?.columns ?? ["Direction", "Entry date", "Entry", "Exit date", "Exit", "Return"]).map(
            (label, index) => ({ label, numeric: index >= 2 }),
          )}
          rows={(model.trades?.rows ?? []).map((cells, index) => ({ key: index, cells }))}
        />
      </section>
    </div>
  );
}
