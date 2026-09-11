/**
 * Word reveal — pinned blur (variant 1). The full-drama reveal, reserved for
 * the one hero claim per page: words fill from blur as the line rides up the
 * viewport — the reveal starts the moment the line enters, completes by
 * mid-viewport, and a short sticky hold gives the finished claim one beat
 * before the page flows on. It can never scroll away half-read. Under reduced
 * motion — or no JS — the final state renders statically. Consumes the shared
 * <WordReveal/> primitive from @digithings/web (promoted #1450); this specimen
 * is a thin wrapper that keeps the catalog rendering it.
 */
import { WordReveal } from "@digithings/web";

const TEXT =
  "Every number here traces to a real backtest nothing is invented and nothing is rounded";

export function WordRevealReference() {
  return (
    <section className="section-block word-reveal" id="word-reveal">
      <p className="kicker">{"// word reveal — pinned blur"}</p>
      <h2 className="title">The claim holds until it is legible.</h2>
      <p className="section-copy">
        The full-drama variant, reserved for the one hero claim per page. Words fill from blur as
        the line rides up the viewport — the reveal starts the moment the line enters, completes
        by mid-viewport, and a short pinned hold gives the finished claim one beat before the page
        flows on. It cannot scroll away half-read; under reduced motion the final state renders
        statically.
      </p>
      <WordReveal text={TEXT} />
    </section>
  );
}
