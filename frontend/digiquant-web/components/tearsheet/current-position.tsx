import type { ReactNode } from "react";
import { DirectionPill, dcaRateCopy, fmtNum, fmtPct, riskBandLabel, toneClass } from "@digithings/web";
import { AssetLogoFor } from "./asset-logo";
import { isDcaTearsheet } from "./dca";
import {
  isOpenTrade,
  markPriceForTrade,
  openTrade,
  unrealizedReturnPct,
} from "./trades";
import { type TearsheetData, type TearsheetTrade } from "./types";

function Toned({ v, children }: { v: number; children: ReactNode }) {
  const c = toneClass(v);
  return c ? <span className={c}>{children}</span> : <>{children}</>;
}

/** Live position banner — always shown; flat when no open leg at period end. */
export function CurrentPosition({ data, asset }: { data: TearsheetData; asset: string }) {
  if (isDcaTearsheet(data)) {
    return <DcaCurrentSignal data={data} asset={asset} />;
  }
  const open = openTrade(data.trades, data.period_end);
  const asOf = data.period_end;

  if (!open) {
    return (
      <section className="ts-position ts-position-flat" aria-label="Current position">
        <div className="ts-position-head">
          <span className="ts-panel-label">Current position</span>
          <span className="ts-position-asof">as of {asOf}</span>
        </div>
        <p className="ts-position-flat-msg">
          Flat on{" "}
          <span className="ts-position-asset">
            <AssetLogoFor strategy={data.strategy} symbol={data.symbol} size={20} className="ts-position-logo" />
            {asset}
          </span>{" "}
          — no open leg at the last bar.
        </p>
      </section>
    );
  }

  const mark = markPriceForTrade(open, data);
  const unr = unrealizedReturnPct(open, mark);
  const signal = open.entry_label?.trim();

  return (
    <section className="ts-position ts-position-live" aria-label="Current position">
      <div className="ts-position-head">
        <span className="ts-panel-label">Current position</span>
        <span className="ts-position-asof">as of {asOf}</span>
      </div>
      <div className="ts-position-body">
        <DirectionPill direction={open.direction} />
        <div className="ts-position-main">
          {signal ? <span className="ts-position-signal">{signal}</span> : null}
          <span className="ts-position-entry">
            Entered {open.entry_date} @ {fmtNum(open.entry_price, 2)}
          </span>
        </div>
        <dl className="ts-position-stats">
          <div>
            <dt>Mark</dt>
            <dd>{fmtNum(mark, 2)}</dd>
          </div>
          <div>
            <dt>Unrealized</dt>
            <dd>
              <Toned v={unr}>{fmtPct(unr)}</Toned>
            </dd>
          </div>
          <div>
            <dt>Asset</dt>
            <dd className="ts-position-asset-dd">
              <AssetLogoFor strategy={data.strategy} symbol={data.symbol} size={20} className="ts-position-logo" />
              {asset}
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

function DcaCurrentSignal({ data, asset }: { data: TearsheetData; asset: string }) {
  const asOf = data.period_end;
  const sig = data.current_signal;
  const risk = sig?.risk ?? data.dca?.avg_risk ?? null;
  const band = sig?.band ?? riskBandLabel(risk);
  const rateCopy = dcaRateCopy(sig?.daily_rate_pct);
  const headline = band
    ? rateCopy
      ? `${band} — ${rateCopy}`
      : band
    : "DCA book";
  const deployed = data.dca?.capital_deployed_pct;
  const units = data.dca?.units_accumulated;
  const lastPrice = sig?.last_price ?? null;

  return (
    <section className="ts-position ts-position-live" aria-label="Current signal">
      <div className="ts-position-head">
        <span className="ts-panel-label">Current signal</span>
        <span className="ts-position-asof">as of {asOf}</span>
      </div>
      <div className="ts-position-body">
        <div className="ts-position-main">
          <span className="ts-position-dca-band">{headline}</span>
          {rateCopy ? null : (
            <span className="ts-position-entry">
              Accumulation book on{" "}
              <span className="ts-position-asset">
                <AssetLogoFor strategy={data.strategy} symbol={data.symbol} size={20} className="ts-position-logo" />
                {asset}
              </span>
            </span>
          )}
        </div>
        <dl className="ts-position-stats">
          <div>
            <dt>Risk</dt>
            <dd>{risk == null ? "—" : risk.toFixed(1)}</dd>
          </div>
          <div>
            <dt>Band</dt>
            <dd>{band ?? "—"}</dd>
          </div>
          <div>
            <dt>Deployed</dt>
            <dd>{fmtPct(deployed)}</dd>
          </div>
          <div>
            <dt>Units</dt>
            <dd>{units == null ? "—" : fmtNum(units, 4)}</dd>
          </div>
          <div>
            <dt>Mark</dt>
            <dd>{fmtNum(lastPrice, 2)}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

/** Trade-log return cell — realized or unrealized. */
export function TradeReturnCell({
  t,
  data,
}: {
  t: TearsheetTrade;
  data: TearsheetData;
}) {
  if (isOpenTrade(t)) {
    const mark = markPriceForTrade(t, data);
    const unr = unrealizedReturnPct(t, mark);
    return (
      <span className="ts-trade-unrealized">
        <Toned v={unr}>{fmtPct(unr)}</Toned>
        <span className="ts-trade-unrealized-tag">unrealized</span>
      </span>
    );
  }
  const c = toneClass(t.pnl_pct);
  return c ? <span className={c}>{fmtPct(t.pnl_pct)}</span> : <>{fmtPct(t.pnl_pct)}</>;
}
