/**
 * Tearsheet cards — the strategy-library card: the whole card is an anchor
 * with hover-lift and an accent border wake over the gradient surface, a
 * mono name/period head with the pulsing LiveBadge on nightly-refreshed
 * entries, and a 2-column KPI grid whose values wear the money tones. This
 * is the dress the promoted controls Card could not express (anchor
 * composition + tearsheet gradient) — the gap #1463 closed. Static display
 * template.
 */
import {
  LiveBadge,
  TearsheetCard,
  TearsheetCardKpi,
  TearsheetCardKpis,
  fmtNum,
  fmtPct,
  toneClass,
} from "@digithings/web";

const CARDS = [
  {
    name: "BTC",
    slug: "btc-long-short",
    period: "2023-01-02 → 2026-02-20",
    live: true,
    kpis: { cagr: 42.7, maxDd: -28.4, pf: 2.31, winRate: 58.3, avgTrade: 3.4, trades: 62 },
  },
  {
    name: "ETH",
    slug: "eth-momentum",
    period: "2023-06-01 → 2026-02-20",
    live: true,
    kpis: { cagr: 18.9, maxDd: -22.1, pf: 1.62, winRate: 51.7, avgTrade: 1.8, trades: 88 },
  },
  {
    name: "SOL",
    slug: "sol-breakout",
    period: "2024-01-08 → 2026-02-20",
    live: false,
    kpis: { cagr: -6.2, maxDd: -41.5, pf: 0.87, winRate: 44.0, avgTrade: -0.6, trades: 51 },
  },
] as const;

export function TearsheetCardReference() {
  return (
    <div className="ts-lib-grid">
      {CARDS.map((c) => (
        <TearsheetCard key={c.slug} href={`#${c.slug}`}>
          <div className="ts-card-head">
            <div className="ts-card-title">
              <div className="ts-card-title-text">
                <span className="ts-card-name">{c.name}</span>
                <span className="ts-card-period">{c.period}</span>
              </div>
            </div>
            {c.live ? <LiveBadge className="ts-card-live" /> : null}
          </div>
          <TearsheetCardKpis>
            <TearsheetCardKpi
              label="CAGR"
              value={<span className={toneClass(c.kpis.cagr)}>{fmtPct(c.kpis.cagr)}</span>}
            />
            <TearsheetCardKpi
              label="Max DD"
              value={<span className="is-neg">{fmtPct(c.kpis.maxDd)}</span>}
            />
            <TearsheetCardKpi label="Profit factor" value={fmtNum(c.kpis.pf, 2)} />
            <TearsheetCardKpi label="Win rate" value={fmtPct(c.kpis.winRate)} />
            <TearsheetCardKpi
              label="Avg trade"
              value={<span className={toneClass(c.kpis.avgTrade)}>{fmtPct(c.kpis.avgTrade)}</span>}
            />
            <TearsheetCardKpi label="Trades" value={fmtNum(c.kpis.trades)} />
          </TearsheetCardKpis>
        </TearsheetCard>
      ))}
    </div>
  );
}
