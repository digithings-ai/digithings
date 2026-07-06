import "./data.css";
import { DotMatrixStat } from "@/components/dot-matrix-stat";
import { PricingReference } from "@/components/pricing-reference";
import { StrategySuiteReference } from "@/components/strategy-suite-reference";

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
      <StrategySuiteReference />
      <PricingReference />
    </main>
  );
}
