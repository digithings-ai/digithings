import { HorizontalScrollTrack, HorizontalTrackStepper } from "@digithings/ui";

/**
 * Horizontal scroll track — the specimen for the shared <HorizontalScrollTrack/>
 * (@digithings/ui, effects-chrome). At 960px and wider, with motion allowed, a
 * sticky pin holds the row while vertical scroll drives it sideways; the runway
 * height is derived from the track's content width, and the translate is a
 * motion-value function transform (no per-frame React state). Below 960px, under
 * reduced motion, on first paint and with no JS, the same cards are a native
 * scroll-snap strip with all of them reachable.
 *
 * Every card is a tab stop in DOM order; focusing an off-screen card scrolls the
 * runway to it. The stage stepper under the row (HorizontalTrackStepper) reads
 * the track's progress from context: a hairline fill scales with scroll and the
 * active stage is marked; each label jumps to its card. The header is a render
 * prop that shows the state the track exposes to children. One pin per page.
 * Static demo copy — the cards are placeholders, not product claims.
 */
const STAGES = [
  { label: "Inputs", note: "What goes in. One line per source." },
  { label: "Research", note: "Directions proposed from the inputs." },
  { label: "Synthesis", note: "Directions merged into candidates." },
  { label: "Selection", note: "Candidates ranked against a rubric." },
  { label: "Decision", note: "A human gate before anything moves." },
  { label: "Learning", note: "Outcomes written back for the next run." },
];

export function HorizontalTrackReference() {
  return (
    <section className="section-block" id="horizontal-track">
      <p className="kicker">{"// horizontal scroll track"}</p>
      <h2 className="title">Scroll down, the row moves sideways.</h2>
      <p className="section-copy">
        The one sanctioned pin: a row of cards translated by scroll progress inside a sticky
        frame, with a runway sized to the row&apos;s own width. Focus a card and the runway follows
        it. Narrow screens and reduced motion get a native snap strip with every card in reach.
      </p>

      <div className="fx-demo">
        <HorizontalScrollTrack
          ariaLabel="Pipeline stages, demo"
          pinTop={56}
          itemClassName="w-[min(82vw,20rem)]"
          header={(s) => (
            <p className="m-0 px-6 font-mono text-[0.68rem] tracking-[0.04em] text-ink-mute">
              {`stage ${String(s.activeIndex + 1).padStart(2, "0")} / ${String(s.count).padStart(2, "0")} · ${s.pinned ? "pinned, scroll to move" : "native strip, swipe to move"}`}
            </p>
          )}
          footer={<HorizontalTrackStepper labels={STAGES.map((s) => s.label)} />}
        >
          {STAGES.map((s, i) => (
            <article key={s.label} className="grid h-full gap-2 border border-hair bg-surface p-5">
              <span className="font-mono text-[0.68rem] tracking-[0.06em] text-ink-mute">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="m-0 font-mono text-[1.05rem] text-ink">{s.label}</h3>
              <p className="m-0 text-[0.85rem] leading-[1.6] text-ink-soft">{s.note}</p>
            </article>
          ))}
        </HorizontalScrollTrack>
      </div>
    </section>
  );
}
