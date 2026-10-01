"use client";

/**
 * DivergingBars + ScoreBar specimen — signed bars on a zero-centred SVG track.
 * DivergingBars ranks labelled values; ScoreBar is the single-row form with
 * reference ticks and a target marker (it replaces the dashboard's app-local
 * ConsensusScoreBar). Signed tone uses up/down; pass `tone="accent"` or a
 * per-row tone for health-style values.
 */
import { DivergingBars, ScoreBar } from "@digithings/ui/ui";

const RANKED = [
  { label: "USD", value: 1.6 },
  { label: "EUR", value: 0.7 },
  { label: "GBP", value: 0.2 },
  { label: "CHF", value: -0.4 },
  { label: "JPY", value: -1.3 },
  { label: "NZD", value: null },
];

export function DivergingBarsReference() {
  return (
    <section className="section-block" id="diverging-bars">
      <p className="kicker">{"// diverging-bars"}</p>
      <h2 className="title">Signed, ranked, labelled.</h2>
      <p className="section-copy">
        <code>DivergingBars</code> and <code>ScoreBar</code> from <code>@digithings/ui</code>.
        Pure SVG tracks; empty values draw an empty track and an em dash.
      </p>

      <div className="mt-[1.2rem] grid gap-[1.2rem] border border-hair p-[1.2rem] md:grid-cols-2">
        <div>
          <p className="kicker">{"// ranked, signed"}</p>
          <DivergingBars items={RANKED} sort="desc" label="Consensus by currency" />
        </div>
        <div>
          <p className="kicker">{"// accent tone"}</p>
          <DivergingBars items={RANKED} sort="abs" tone="accent" label="Conviction by currency" />
        </div>
        <div className="md:col-span-2">
          <p className="kicker">{"// score bar: ticks + target"}</p>
          <div className="grid max-w-md gap-2">
            <ScoreBar min={-2} max={2} value={1.1} label="USD" />
            <ScoreBar
              min={-2}
              max={2}
              value={-0.6}
              label="JPY"
              ticks={[
                { value: -0.2, label: "yesterday", tone: "accent" },
                { value: 0.3, label: "5d ago", tone: "mute" },
              ]}
              target={{ value: -1, label: "target" }}
            />
            <ScoreBar min={-2} max={2} value={null} label="NZD" />
          </div>
        </div>
      </div>
    </section>
  );
}
