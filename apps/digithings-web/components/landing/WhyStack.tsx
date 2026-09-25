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
 * finishes, the page pushes the owned diagram in and the camera takes over.
 * The static pair, the capability table and the cost model that shared the
 * variants page are NOT here — he asked for the walk alone.
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
                  <span className="why-rent">Rent the whole stack,</span>{" "}
                  <span className="text-accent">or own every layer.</span>
                </h2>
                <p className={LEDE}>
                  Buy a managed platform and you rent one shape, priced for the average customer, on
                  somebody else&rsquo;s release schedule. Build on digithings and you run the same
                  architecture as your own — every layer a piece you can swap, on your hosts, with
                  your keys, at your provider&rsquo;s own rates. Scroll to watch one become the
                  other: the stack you rent, then the stack you own.
                </p>
              </>
            }
            sides={[
              { spec: CONVENTIONAL_ARCH, steps: RENTED_TOUR_STEPS, tag: "rented", rail: "end" },
              { spec: DIGITHINGS_ARCH, steps: OWNED_TOUR_STEPS, tag: "owned" },
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
