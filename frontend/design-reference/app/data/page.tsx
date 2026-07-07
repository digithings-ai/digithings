import "./data.css";
import { CardDeck, type CardDeckItem } from "@/components/card-deck";
import { ChangelogRailReference } from "@/components/changelog-rail-reference";
import { AlertCard, ChangelogCard, MetricCard, QuoteCard } from "@/components/deck-cards";
import { DotMatrixStat } from "@/components/dot-matrix-stat";
import { MarqueeTickerReference } from "@/components/marquee-ticker-reference";
import { PricingMatrixReference } from "@/components/pricing-matrix-reference";
import { PricingReference } from "@/components/pricing-reference";
import { RoadmapGanttReference } from "@/components/roadmap-gantt-reference";
import { StatCounterReference } from "@/components/stat-counter-reference";

const DECK: CardDeckItem[] = [
  {
    id: "deck-metric",
    railLabel: "Tearsheet",
    content: (
      <MetricCard
        name="BTC Slapper"
        summary="Trend-following, 1D bars, long/short."
        ordinal={1}
        cagr="+44.9%"
        maxDd="-54.1%"
        pf="2.31"
      />
    ),
  },
  {
    id: "deck-changelog",
    railLabel: "Changelog",
    content: (
      <ChangelogCard
        version="v2.4.1"
        date="2026-06-28"
        entries={[
          "Added a flat-state guard to the momentum gate.",
          "Fixed drawdown accounting across session boundaries.",
          "Removed the legacy resampler; Polars end to end.",
        ]}
      />
    ),
  },
  {
    id: "deck-quote",
    railLabel: "Quote",
    content: (
      <QuoteCard
        quote="A backtest is a rumor. A tearsheet you can re-run is a receipt."
        attribution="Design notes, 2026"
      />
    ),
  },
  {
    id: "deck-alert",
    railLabel: "Incident",
    content: (
      <AlertCard
        status="Investigating"
        tone="down"
        timestamp="09:42 UTC"
        title="Websocket feed degraded"
        impact="Live bars delayed up to 40s on ETH pairs; backtests unaffected."
      />
    ),
  },
];

export default function DataPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// data"}</p>
        <h1>
          Numbers, <em>glance-readable.</em>
        </h1>
        <p>
          Data display grammar: dot-matrix stats, the card deck, and precision tables — mono
          numerals, hairline rows, honest units.
        </p>
      </header>

      <DotMatrixStat />
      <StatCounterReference />
      <MarqueeTickerReference />

      <section className="section-block" id="card-deck">
        <p className="kicker">{"// card deck"}</p>
        <h2 className="title">Cards stack as you scroll.</h2>
        <p className="section-copy">
          The deck knows nothing about its cards: a tearsheet, a changelog, a pull-quote, and an
          incident report share one engine. On wide screens each card pins and the next slides
          over it, edges cascading; on narrow screens they simply appear in sequence.
        </p>
        <CardDeck ariaLabel="Card stack" items={DECK} />
      </section>

      <ChangelogRailReference />
      <RoadmapGanttReference />
      <PricingReference />
      <PricingMatrixReference />
    </main>
  );
}
