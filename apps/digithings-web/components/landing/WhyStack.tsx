/**
 * The `#why` guided walk (round 15, #4429).
 *
 * The owner picked the "02 · guided, rented then owned" composition from the
 * `/variants/why` page and asked for exactly that in the band: "all i wanted
 * was the 02 · guided, rented then owned with the diagram view of owned and
 * rented, nothing else."
 *
 * So the band is the walk by itself. It opens on the rented C4 container
 * diagram and glows each box it is talking about; when the rented walk
 * finishes, the page pushes the digithings diagram in and the camera takes over.
 * The static pair, the capability table and the cost model that shared the
 * variants page are NOT here — he asked for the walk alone.
 *
 * v16 brands the frame, not the boxes: the headline, side tags, diagram
 * titles and captions name the digithings stack, while the boxes keep their
 * generic their/your grammar (naming boxes after modules would turn a shape
 * critique into a vendor pitch and pin the flagship visual to today's module
 * list). The contrast is who holds the seams, not rent-vs-own as property —
 * and the walk resolves on partial adoption (one layer or the whole stack).
 *
 * Server component: the tour is the only client piece and is a client
 * component in its own right (`<ArchitectureTour>` lazily imports mermaid), so
 * nothing here ships a bundle.
 */

import { ArchitectureTour } from "@digithings/ui";

import { CONVENTIONAL_ARCH, DIGITHINGS_ARCH, OWNED_TOUR_STEPS, RENTED_TOUR_STEPS } from "@/lib/whyStack";

const HEADLINE = "m-0 font-mono text-[clamp(1.3rem,2.4vw,1.85rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink";
const LEDE = "m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft";

function Tour() {
  return (
    <section className="whyx__block" aria-labelledby="whyx-tour">
      <div className="whyx__tours">
        <div className="whyx__tour">
          <ArchitectureTour
            header={
              <>
                <h2 className={HEADLINE} id="whyx-tour">
                  <span className="why-rent">Their AI stack,</span>{" "}
                  <span className="why-own">or the digithings stack.</span>
                </h2>
                <p className={LEDE}>
                  An off-the-shelf AI platform rents you one fixed shape — models, index, data
                  and machines behind a single interface, on somebody else&rsquo;s release
                  schedule. digithings is the same AI infrastructure as pieces you run
                  yourself, on your hosts and keys — starting with whichever layer hurts
                  most. Scroll to watch one become the other: the stack you rent, then the
                  digithings stack.
                </p>
              </>
            }
            sides={[
              {
                spec: CONVENTIONAL_ARCH,
                steps: RENTED_TOUR_STEPS,
                tag: "rented stack",
                rail: "end",
                caption: "Every edge metered — per-token · per-query · per-gigabyte",
              },
              {
                spec: DIGITHINGS_ARCH,
                steps: OWNED_TOUR_STEPS,
                tag: "digithings stack",
                caption: "Same calls, your rates — swap it · you choose · yours",
              },
            ]}
            variant="camera"
          />
        </div>
      </div>
    </section>
  );
}

export function WhyStack() {
  return (
    <div className="whyx">
      <Tour />
    </div>
  );
}
