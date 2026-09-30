"use client";

/**
 * RangeTrack specimen — a low..high track with entry / current / stop / target
 * markers. Lifts the RiskEnvelopeCell math: `envelopeRange` gives the percent-
 * vs-entry axis, a reading past an end pins there with a caret, and a
 * zero-width or missing range draws nothing (never a fabricated midpoint).
 */
import { RangeTrack, envelopeRange } from "@digithings/ui/ui";

const pct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;

export function RangeTrackReference() {
  const env = envelopeRange(-6, 12);
  return (
    <section className="section-block" id="range-track">
      <p className="kicker">{"// range-track"}</p>
      <h2 className="title">Where it sits in the range.</h2>
      <p className="section-copy">
        <code>RangeTrack</code> from <code>@digithings/ui</code>: levels as tick markers, the
        current reading as a taller bar, out-of-range readings pinned with a caret.
      </p>

      <div className="mt-[1.2rem] grid max-w-md gap-4 border border-hair p-[1.2rem]">
        <RangeTrack
          {...env}
          envelope
          showEnds
          format={pct}
          label="Risk envelope"
          markers={[
            { kind: "stop", value: env.low, label: "Stop" },
            { kind: "entry", value: 0, label: "Entry" },
            { kind: "target", value: env.high, label: "Target" },
            { kind: "current", value: 3.4, label: "Now" },
          ]}
        />
        <RangeTrack
          {...env}
          envelope
          format={pct}
          label="Risk envelope (through target)"
          markers={[
            { kind: "entry", value: 0 },
            { kind: "current", value: 15, label: "Now" },
          ]}
        />
        <RangeTrack
          low={1.05}
          high={1.12}
          showEnds
          label="Day range"
          markers={[
            { kind: "level", value: 1.08, label: "Pivot" },
            { kind: "current", value: 1.095, label: "Last" },
          ]}
        />
        <RangeTrack low={0} high={0} markers={[{ value: 0 }]} />
      </div>
    </section>
  );
}
