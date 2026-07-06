import "./data.css";
import { CardDeck, type CardDeckItem } from "@/components/card-deck";
import { AlertCard, ChangelogCard, MetricCard, QuoteCard } from "@/components/deck-cards";
import { DotMatrixStat } from "@/components/dot-matrix-stat";
import { PricingReference } from "@/components/pricing-reference";

const STRATEGIES = [
  {
    name: "BTC Slapper",
    summary: "Trend-following, 1D bars, long/short.",
    cagr: "+44.9%",
    maxDd: "-54.1%",
    pf: "2.31",
  },
  {
    name: "ETH Slapper",
    summary: "Cross-regime momentum with flat-state guard.",
    cagr: "+38.1%",
    maxDd: "-49.7%",
    pf: "2.12",
  },
  {
    name: "SOL Slapper",
    summary: "Higher-volatility profile with tighter risk cap.",
    cagr: "+52.4%",
    maxDd: "-59.2%",
    pf: "2.58",
  },
];

const STRATEGY_DECK: CardDeckItem[] = STRATEGIES.map((strategy, idx) => ({
  id: strategy.name,
  railLabel: strategy.name,
  content: <MetricCard {...strategy} ordinal={idx + 1} />,
}));

const MIXED_DECK: CardDeckItem[] = [
  {
    id: "mixed-metric",
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
    id: "mixed-changelog",
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
    id: "mixed-quote",
    railLabel: "Quote",
    content: (
      <QuoteCard
        quote="A backtest is a rumor. A tearsheet you can re-run is a receipt."
        attribution="Design notes, 2026"
      />
    ),
  },
  {
    id: "mixed-alert",
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

      <section className="section-block" id="strategy-suite">
        <p className="kicker">{"// strategy suite"}</p>
        <h2 className="title">Sticky peek stack + rail, React-native.</h2>
        <p className="section-copy">
          Three tearsheets on one generic deck. Scroll promotes the next card to the front, the
          mono rail tracks position, and below 900px the pin releases into a plain stacked list.
        </p>
        <CardDeck ariaLabel="Strategy tearsheet stack" items={STRATEGY_DECK} />
      </section>

      <section className="section-block" id="mixed-deck">
        <p className="kicker">{"// mixed deck"}</p>
        <h2 className="title">Same engine, any content.</h2>
        <p className="section-copy">
          The deck knows nothing about its cards: a tearsheet, a changelog, a pull-quote, and an
          incident report share one scroll engine, one rail, one degradation path.
        </p>
        <CardDeck ariaLabel="Mixed content stack" items={MIXED_DECK} />
      </section>

      <PricingReference />
    </main>
  );
}
