/**
 * Figure — the numbered `Fig N` figure grammar (D1, #4429): any content plus a
 * mono caption led by the accent `Fig N` label. Shown here wrapping the shared
 * OdometerStrip, the way the landing metrics band uses it. Static display
 * template.
 */
import { Figure, OdometerStrip, type OdometerStat } from "@digithings/ui";

const STATS: OdometerStat[] = [
  { label: "modules shipping", value: "9" },
  { label: "compose services", value: "23" },
  { label: "vector backends", value: "3" },
  { label: "keys stored", value: "0" },
];

export function FigureReference() {
  return (
    <section className="section-block figure-reference">
      <p className="kicker">{"// figure"}</p>
      <h2 className="title">Numbers, numbered.</h2>
      <p className="section-copy">
        The <code>Fig N</code> grammar: a figure with a mono caption that leads with the accent
        label, so a stat block reads as a labelled exhibit rather than an unanchored number. Any
        content works — a strip, a media frame, a diagram.
      </p>

      <Figure n={1} caption="the metrics strip, counted from the repository" className="mt-[1.2rem]">
        <OdometerStrip stats={STATS} />
      </Figure>
    </section>
  );
}
